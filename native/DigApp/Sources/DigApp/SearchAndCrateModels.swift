// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI
import AppKit
import Observation

struct SearchResultRow: Decodable, Identifiable, Hashable {

    let username: String
    let virtualPath: String
    let folder: String
    let filename: String
    let size: Int64
    let bitrate: Int?
    let length: Int?
    let vbr: Int?
    let sampleRate: Int?
    let bitDepth: Int?
    let slotAvailable: Bool
    let uploadSpeed: Int
    let queuePosition: Int
    let privateShare: Bool

    var id: String { username + "/" + virtualPath }

    enum CodingKeys: String, CodingKey {
        case username, folder, filename, size, bitrate, length, vbr
        case virtualPath = "virtual_path"
        case sampleRate = "sample_rate"
        case bitDepth = "bit_depth"
        case slotAvailable = "slot_available"
        case uploadSpeed = "upload_speed"
        case queuePosition = "queue_position"
        case privateShare = "private"
    }

    var asFile: SharedFileRow {
        SharedFileRow(
            name: filename,
            size: size,
            bitrate: bitrate,
            length: length,
            vbr: vbr,
            sampleRate: sampleRate,
            bitDepth: bitDepth
        )
    }
}

struct SearchResultsPage: Decodable {
    let total: Int
    let offset: Int
    let limit: Int
    let results: [SearchResultRow]
}

struct SearchGroup: Identifiable {

    let username: String
    let results: [SearchResultRow]

    var id: String { username }
}

@MainActor
@Observable
final class SearchModel {

    var client: EngineClient?
    var term = ""
    var token: Int?
    var results: [SearchResultRow] = []
    var total = 0
    var isSearching = false
    var error = ""
    var selectedID: String?

    var selected: SearchResultRow? {
        results.first { $0.id == selectedID }
    }

    /// Peers in first-appearance order, so the list stays stable as results land.
    var groups: [SearchGroup] {

        var order: [String] = []
        var buckets: [String: [SearchResultRow]] = [:]

        for result in results {
            if buckets[result.username] == nil {
                order.append(result.username)
            }

            buckets[result.username, default: []].append(result)
        }

        return order.map { SearchGroup(username: $0, results: buckets[$0] ?? []) }
    }

    func run() async {

        guard let client else {
            error = "The engine is not connected yet. Wait for the status light, then search."
            return
        }

        let query = term.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !query.isEmpty else { return }

        isSearching = true
        error = ""
        results = []
        total = 0
        token = nil
        selectedID = nil

        do {
            let summary = try await client.startSearch(term: query)
            token = summary.token

            var stable = 0
            var lastTotal = -1

            // ~24 s ceiling; searches normally settle in two or three ticks.
            for _ in 0..<30 {
                try? await Task.sleep(nanoseconds: 800_000_000)

                guard let page = try? await client.searchResults(token: summary.token, offset: 0, limit: 500) else {
                    continue
                }

                results = page.results
                total = page.total

                if selectedID == nil {
                    selectedID = results.first?.id
                }

                if page.total == lastTotal {
                    stable += 1

                    if stable >= 3 {
                        break
                    }
                } else {
                    stable = 0
                    lastTotal = page.total
                }
            }

            if results.isEmpty {
                error = "No results. The network can be quiet for white labels and promos; try a shorter term."
            }

        } catch {
            self.error = error.localizedDescription
        }

        isSearching = false
    }

    func loadMore() async {

        guard let client, let token, results.count < total else { return }

        guard let page = try? await client.searchResults(
            token: token, offset: results.count, limit: 500) else { return }

        results.append(contentsOf: page.results)
        total = page.total
    }
}

@MainActor
@Observable
final class CrateModel {

    var client: EngineClient?
    var tracks: [CrateTrack] = []
    var selectedID: String?
    var error = ""
    var isLoading = false

    var selected: CrateTrack? {
        tracks.first { $0.id == selectedID }
    }

    func load() async {

        guard let client else { return }

        isLoading = true

        do {
            let page = try await client.crate()
            tracks = page.tracks

            if selectedID == nil {
                selectedID = tracks.first?.id
            }

        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func separate(id: String) async {
        guard let client else { return }
        try? await client.separateCrateTrack(id: id)
        await load()
    }
}
