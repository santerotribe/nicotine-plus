// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

enum VirtualPath {

    /// Soulseek separates folders with a single backslash.
    static func join(folder: String, name: String) -> String {
        folder.isEmpty ? name : folder + "\\" + name
    }
}

/// Peer browse: paged folders and files, driven by the engine's paging endpoints.
@MainActor
@Observable
final class BrowserModel {

    struct FolderRow: Identifiable, Hashable {

        let name: String
        let count: Int
        let size: Int64
        let audioFiles: Int
        let audioFormats: [String: Int]
        let lossless: Int
        let seconds: Int

        var id: String { name }

        var title: String {
            name.split(separator: "\\").last.map(String.init) ?? name
        }

        var depth: Int {
            max(0, name.split(separator: "\\").count - 1)
        }

        var sizeLabel: String {
            ByteCountFormatter.string(fromByteCount: size, countStyle: .binary)
        }

        /// "FLAC 9 · MP3 1", most common first.
        var qualityLabel: String {
            audioFormats.sorted { $0.value > $1.value }
                .prefix(2)
                .map { "\($0.key.uppercased()) \($0.value)" }
                .joined(separator: " · ")
        }

        /// Lossless share of the audio, never of the covers and cue sheets.
        var losslessRatio: Double {
            audioFiles > 0 ? Double(lossless) / Double(audioFiles) : 0
        }

        /// "CD 4", "FLAC" and "Disc 2" say nothing on their own; the album or
        /// collection above them does. These leaves inherit that context.
        var isGeneric: Bool {
            FolderRow.isGenericLeaf(title)
        }

        var collectionTitle: String {

            var parts = name.split(separator: "\\").map(String.init)

            guard parts.count > 1 else { return "" }

            parts.removeLast()

            while parts.count > 1, let last = parts.last, FolderRow.isGenericLeaf(last) {
                parts.removeLast()
            }

            // Only the share root is left: it names the seller's drive, not
            // the record, so it is not useful context.
            guard parts.count > 1 else { return "" }

            return parts.last ?? ""
        }

        static func isGenericLeaf(_ value: String) -> Bool {

            let lower = value.lowercased().trimmingCharacters(in: .whitespaces)

            let plain: Set<String> = [
                "flac", "mp3", "wav", "aiff", "aif", "m4a", "lossless",
                "music", "misc", "other", "stuff", "new", "downloads",
                "albums", "cd", "disc", "disk",
            ]

            if plain.contains(lower) {
                return true
            }

            return lower.range(
                of: #"^(cd|disc|disk|part|vol|volume)[\s._-]*\d{1,3}$"#,
                options: .regularExpression
            ) != nil
        }
    }

    enum BinSort: String, CaseIterable, Identifiable {

        case promising, fresh, name, files

        var id: String { rawValue }

        var title: String {
            switch self {
            case .promising: "Promising"
            case .fresh: "New"
            case .name: "Name"
            case .files: "Files"
            }
        }
    }

    var client: EngineClient?
    var users: [String] = []
    var selectedUser: String?
    var summary: BrowseSummary?
    var folders: [FolderRow] = []
    var selectedFolder: String?
    var files: [SharedFileRow] = []
    var fileTotal = 0
    var filter = ""
    /// Narrows the folder column without touching the share itself.
    var folderFilter = ""
    /// Folders as cards rather than rows.
    var binGrid = true
    var binSort: BinSort = .promising
    /// Folders that appeared or grew since this peer's last visit.
    var fresh: Set<String> = []
    /// Set when a dig selects a folder, so the grid centres once, not on
    /// every click.
    var scrollToSelection = false
    private var baselines: [String: SeenSnapshot] = [:]
    var isLoading = false
    var isBrowsing = false
    var error = ""
    /// Short-lived confirmation after a bulk action, shown in the shelf header.
    var note = ""

    var filteredFolders: [FolderRow] {

        let query = folderFilter.trimmingCharacters(in: .whitespaces)

        guard !query.isEmpty else { return folders }

        return folders.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }

    var sortedFolders: [FolderRow] {

        let base = filteredFolders

        switch binSort {
        case .name:
            return base.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }

        case .files:
            return base.sorted { $0.count > $1.count }

        case .promising:
            return base.sorted {
                if $0.losslessRatio != $1.losslessRatio { return $0.losslessRatio > $1.losslessRatio }
                if $0.count != $1.count { return $0.count > $1.count }
                return $0.name.localizedStandardCompare($1.name) == .orderedAscending
            }

        case .fresh:
            return base.sorted {
                let leftFresh = fresh.contains($0.name)
                let rightFresh = fresh.contains($1.name)

                if leftFresh != rightFresh { return leftFresh }
                if $0.losslessRatio != $1.losslessRatio { return $0.losslessRatio > $1.losslessRatio }
                return $0.count > $1.count
            }
        }
    }

    private struct SeenSnapshot: Codable {
        var counts: [String: Int]
        var sizes: [String: Int64]
        var updated: Double
    }

    /// Compare the share with the last visit. A folder is fresh when it is new,
    /// has gained files, or has grown in bytes (a replaced file changes size
    /// without changing the count). The baseline is advanced when the visit
    /// ends, never on every load, so the markers survive a Refresh.
    private func noteFresh(user: String) {

        let snapshot = baseline(for: user)

        if snapshot.counts.isEmpty {
            fresh = []
            return
        }

        fresh = Set(folders.filter { folder in
            guard let count = snapshot.counts[folder.name] else { return true }

            if folder.count > count {
                return true
            }

            return folder.size > (snapshot.sizes[folder.name] ?? 0)
        }.map(\.name))
    }

    private func baseline(for user: String) -> SeenSnapshot {

        if let cached = baselines[user] {
            return cached
        }

        let snapshot: SeenSnapshot

        if let data = UserDefaults.standard.data(forKey: "seenFolders.v2." + user),
           let decoded = try? JSONDecoder().decode(SeenSnapshot.self, from: data) {
            snapshot = decoded
        } else {
            snapshot = SeenSnapshot(counts: [:], sizes: [:], updated: 0)
        }

        baselines[user] = snapshot

        return snapshot
    }

    /// Called when the shelf is left, the peer changes, or the app quits.
    func commitSeen() {

        guard let user = selectedUser, !folders.isEmpty else { return }

        var counts: [String: Int] = [:]
        var sizes: [String: Int64] = [:]

        for folder in folders {
            counts[folder.name] = folder.count
            sizes[folder.name] = folder.size
        }

        let snapshot = SeenSnapshot(
            counts: counts,
            sizes: sizes,
            updated: Date().timeIntervalSince1970
        )

        baselines[user] = snapshot

        if let data = try? JSONEncoder().encode(snapshot) {
            UserDefaults.standard.set(data, forKey: "seenFolders.v2." + user)
        }

        pruneSeen()
    }

    /// A collective browses a lot of peers; keep the ledger to a season.
    private func pruneSeen() {

        let cutoff = Date().timeIntervalSince1970 - 60 * 24 * 60 * 60
        let prefix = "seenFolders.v2."
        let defaults = UserDefaults.standard

        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
            guard let data = defaults.data(forKey: key),
                  let snapshot = try? JSONDecoder().decode(SeenSnapshot.self, from: data) else {
                defaults.removeObject(forKey: key)
                continue
            }

            if snapshot.updated < cutoff {
                defaults.removeObject(forKey: key)
                baselines.removeValue(forKey: String(key.dropFirst(prefix.count)))
            }
        }
    }

    var filteredFiles: [SharedFileRow] {
        guard !filter.isEmpty else { return files }
        return files.filter { $0.name.localizedCaseInsensitiveContains(filter) }
    }

    func adoptBrowsedUsers(_ names: [String]) {

        for name in names where !users.contains(name) {
            users.append(name)
        }
    }

    func browse(user: String) async {

        guard let client else { return }

        if let previous = selectedUser, previous != user {
            commitSeen()
        }

        selectedUser = user
        error = ""

        // The engine already holds this share: use it instead of asking the
        // peer again, which would blank the shelf while the answer is rebuilt.
        if let cached = try? await client.summary(user: user), cached.folders > 0 {
            summary = cached
            isBrowsing = false
            await loadFolders(user: user)
            return
        }

        isBrowsing = true
        summary = nil
        folders = []
        files = []
        selectedFolder = nil

        do {
            try await client.browse(user: user)

            // Own shares answer immediately; a peer's list settles when it lands.
            // Big shares take a while to serialise; the engine keeps the
            // request open, so wait a minute before calling the peer silent.
            for _ in 0..<120 {
                try? await Task.sleep(nanoseconds: 500_000_000)

                if let snapshot = try? await client.summary(user: user), snapshot.folders > 0 {
                    summary = snapshot
                    await loadFolders(user: user)
                    isBrowsing = false
                    return
                }
            }

            error = "No answer yet. The peer may be offline or not sharing."

        } catch {
            self.error = error.localizedDescription
        }

        isBrowsing = false
    }

    func select(user: String) async {

        selectedUser = user

        guard let client else { return }

        if let snapshot = try? await client.summary(user: user) {
            summary = snapshot
            await loadFolders(user: user)
            return
        }

        await browse(user: user)
    }

    func reloadCurrent() async {

        guard let user = selectedUser, let client else { return }

        if let snapshot = try? await client.summary(user: user) {
            summary = snapshot
            await loadFolders(user: user, keepSelection: true)
        }
    }

    func loadFolders(user: String, keepSelection: Bool = false) async {

        guard let client else { return }

        var collected: [FolderRow] = []
        var offset = 0

        while true {
            guard let page = try? await client.folders(user: user, offset: offset, limit: 500) else { break }

            collected.append(contentsOf: page.folders
                .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
                .map {
                    FolderRow(
                        name: $0.name,
                        count: $0.files,
                        size: $0.size,
                        audioFiles: $0.audioFiles,
                        audioFormats: $0.audioFormats,
                        lossless: $0.lossless,
                        seconds: Int($0.duration)
                    )
                })

            offset += page.folders.count

            if offset >= page.total || page.folders.isEmpty { break }
        }

        folders = collected
        noteFresh(user: user)

        let previous = selectedFolder

        if keepSelection, let previous, collected.contains(where: { $0.name == previous }) {
            await loadFiles(folder: previous)
            return
        }

        if let first = collected.first {
            await loadFiles(folder: first.name)
        }
    }

    func loadFiles(folder: String) async {

        guard let client, let user = selectedUser else { return }

        selectedFolder = folder
        files = []
        fileTotal = 0
        error = ""

        guard let page = try? await client.files(user: user, folder: folder, offset: 0, limit: 500) else {
            return
        }

        files = page.files
        fileTotal = page.total
    }

    /// Select one folder in the loaded share, for a dig from a search result.
    /// Case differences happen; the share's spelling wins.
    func focus(folder: String) async {

        guard !folder.isEmpty else { return }

        if folders.contains(where: { $0.name == folder }) {
            await loadFiles(folder: folder)
            scrollToSelection = true
            return
        }

        if let match = folders.first(where: {
            $0.name.localizedCaseInsensitiveCompare(folder) == .orderedSame
        }) {
            await loadFiles(folder: match.name)
            scrollToSelection = true
            return
        }

        guard !folders.isEmpty else { return }

        error = "The peer lists \(folders.count) folders, but not that one."
    }

    func loadMoreFiles() async {

        guard let client, let user = selectedUser, let folder = selectedFolder,
              files.count < fileTotal else { return }

        guard let page = try? await client.files(
            user: user, folder: folder, offset: files.count, limit: 500) else { return }

        files.append(contentsOf: page.files)
        fileTotal = page.total
    }
}
