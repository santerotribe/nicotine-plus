// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

private let rolodexRelative: RelativeDateTimeFormatter = {
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .short
    return formatter
}()

/// The collective's source list: every peer a keep came from, plus the ones
/// starred by hand. A card is a seller, not a scoreboard.
@MainActor
@Observable
final class RolodexModel {

    struct Source: Identifiable {

        let username: String
        var keeps = 0
        var dj = 0
        var sample = 0
        var folders: [String: Int] = [:]
        var lastAdded = 0.0
        var starred = false
        var crew = 0
        var foundBy: Set<String> = []

        var id: String { username }

        var folderCount: Int { folders.count }

        var topFolder: String? {
            folders.max { left, right in
                if left.value != right.value { return left.value < right.value }
                return left.key > right.key  // deterministic on ties
            }?.key
        }

        var topFolderName: String? {
            topFolder?.split(separator: "\\").last.map(String.init)
        }

        var lastLabel: String {
            guard lastAdded > 0 else { return "" }
            return rolodexRelative.localizedString(
                for: Date(timeIntervalSince1970: lastAdded),
                relativeTo: Date()
            )
        }

        var statsLabel: String {
            let mine = "\(keeps) \(keeps == 1 ? "KEEP" : "KEEPS")"

            if crew > 0 {
                return "\(mine) · \(crew) CREW · \(dj) DJ"
            }

            return "\(mine) · \(dj) DJ · \(sample) SAMPLE"
        }

        var foundByList: String {
            foundBy.sorted().joined(separator: ", ")
        }
    }

    var client: EngineClient?
    var tracks: [CrateTrack] = []
    var ledger: [RolodexEntry] = []
    var member = ""
    var statuses: [String: String] = [:]
    var filter = ""
    var isLoading = false

    private var starredPeers: Set<String> = []

    var sources: [Source] {

        let query = filter.trimmingCharacters(in: .whitespaces)
        let built = build()

        let filtered = query.isEmpty ? built : built.filter { source in
            source.username.localizedCaseInsensitiveContains(query)
                || (source.topFolderName?.localizedCaseInsensitiveContains(query) ?? false)
        }

        return filtered.sorted {
            if $0.starred != $1.starred { return $0.starred }
            if $0.lastAdded != $1.lastAdded { return $0.lastAdded > $1.lastAdded }
            return $0.keeps > $1.keeps
        }
    }

    func load() async {

        guard let client, !isLoading else { return }

        isLoading = true

        if let page = try? await client.crate() {
            tracks = page.tracks
        }

        starredPeers = Set(UserDefaults.standard.stringArray(forKey: "rolodex.starred") ?? [])

        if let page = try? await client.rolodex() {
            ledger = page.entries
            member = page.member

            let ledgerStars = Set(page.entries.filter { $0.kind == "star" }.map(\.peer))
            starredPeers.formUnion(ledgerStars)

            // One-time migration: stars that only exist locally are pushed to
            // the shared ledger so the crew sees them too.
            for peer in starredPeers where !ledgerStars.contains(peer) {
                try? await client.starPeer(peer: peer, starred: true)
            }
        }

        isLoading = false

        Task { await self.refreshStatuses() }
    }

    /// Ask the server about each source once, then read the answers back. The
    /// request is asynchronous on the Soulseek side, hence the short pause.
    func refreshStatuses() async {

        guard let client else { return }

        let names = Array(sources.prefix(40).map(\.username))

        guard !names.isEmpty else { return }

        for name in names {
            try? await client.requestUserStatus(user: name)
        }

        // The server answers asynchronously; poll briefly instead of assuming
        // one fixed pause is enough.
        for _ in 0..<6 {
            try? await Task.sleep(nanoseconds: 1_000_000_000)

            var pending = false

            for name in names where statuses[name] == nil {
                if let row = try? await client.userStatus(user: name), row.status != "unknown" {
                    statuses[name] = row.status
                } else {
                    pending = true
                }
            }

            if !pending {
                break
            }
        }
    }

    func toggleStar(_ username: String) async {

        let starred = !starredPeers.contains(username)

        if let client {
            try? await client.starPeer(peer: username, starred: starred)
        }

        if starred {
            starredPeers.insert(username)
        } else {
            starredPeers.remove(username)
        }

        UserDefaults.standard.set(Array(starredPeers).sorted(), forKey: "rolodex.starred")
    }

    func isStarred(_ username: String) -> Bool {
        starredPeers.contains(username)
    }

    private func build() -> [Source] {

        var map: [String: Source] = [:]

        for track in tracks where !track.username.isEmpty {
            var source = map[track.username] ?? Source(username: track.username)

            source.keeps += 1

            if track.kind == "dj" {
                source.dj += 1
            } else {
                source.sample += 1
            }

            let folder = folderPath(track.virtualPath)

            if !folder.isEmpty {
                source.folders[folder, default: 0] += 1
            }

            source.lastAdded = max(source.lastAdded, track.addedAt ?? 0)
            source.starred = starredPeers.contains(track.username)
            map[track.username] = source
        }

        // The collective ledger adds peers and counts from other members.
        for entry in ledger where !entry.peer.isEmpty {
            if entry.kind == "star" {
                continue
            }

            var source = map[entry.peer] ?? Source(username: entry.peer)

            if !entry.folder.isEmpty {
                source.folders[entry.folder, default: 0] += 1
            }

            // "Crew" means someone else: your own keeps are already counted.
            if !entry.foundBy.isEmpty, entry.foundBy != member {
                source.crew += 1
                source.foundBy.insert(entry.foundBy)
            }

            source.lastAdded = max(source.lastAdded, entry.addedAt)
            source.starred = starredPeers.contains(entry.peer)
            map[entry.peer] = source
        }

        // A starred peer with nothing kept yet is still a source worth keeping.
        for peer in starredPeers where map[peer] == nil {
            map[peer] = Source(username: peer, starred: true)
        }

        return Array(map.values)
    }

    private func folderPath(_ virtualPath: String) -> String {

        let parts = virtualPath.split(separator: "\\")

        guard parts.count > 1 else { return "" }

        return parts.dropLast().joined(separator: "\\")
    }
}
