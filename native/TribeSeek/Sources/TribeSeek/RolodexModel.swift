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

        var id: String { username }

        var folderCount: Int { folders.count }

        var topFolder: String? {
            folders.max { $0.value < $1.value }?.key
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
    }

    var client: EngineClient?
    var tracks: [CrateTrack] = []
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

        guard let client else { return }

        isLoading = true

        if let page = try? await client.crate() {
            tracks = page.tracks
        }

        starredPeers = Set(UserDefaults.standard.stringArray(forKey: "rolodex.starred") ?? [])

        isLoading = false

        Task { await self.refreshStatuses() }
    }

    /// Ask the server about each source once, then read the answers back. The
    /// request is asynchronous on the Soulseek side, hence the short pause.
    func refreshStatuses() async {

        guard let client else { return }

        let names = Array(sources.prefix(120).map(\.username))

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

    func toggleStar(_ username: String) {

        if starredPeers.contains(username) {
            starredPeers.remove(username)
        } else {
            starredPeers.insert(username)
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
