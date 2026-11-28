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

        var id: String { name }

        var title: String {
            name.split(separator: "\\").last.map(String.init) ?? name
        }

        var depth: Int {
            max(0, name.split(separator: "\\").count - 1)
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
    var isLoading = false
    var isBrowsing = false
    var error = ""

    var filteredFolders: [FolderRow] {

        let query = folderFilter.trimmingCharacters(in: .whitespaces)

        guard !query.isEmpty else { return folders }

        return folders.filter { $0.name.localizedCaseInsensitiveContains(query) }
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
                .sorted { $0.key.localizedStandardCompare($1.key) == .orderedAscending }
                .map { FolderRow(name: $0.key, count: $0.value) })

            offset += page.folders.count

            if offset >= page.total || page.folders.isEmpty { break }
        }

        folders = collected

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
            return
        }

        if let match = folders.first(where: {
            $0.name.localizedCaseInsensitiveCompare(folder) == .orderedSame
        }) {
            await loadFiles(folder: match.name)
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
