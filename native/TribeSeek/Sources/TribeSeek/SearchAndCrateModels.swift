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
    let dropped: Int
    let offset: Int
    let limit: Int
    let results: [SearchResultRow]

    enum CodingKeys: String, CodingKey {
        case total, dropped, offset, limit, results
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        total = try container.decode(Int.self, forKey: .total)
        dropped = try container.decodeIfPresent(Int.self, forKey: .dropped) ?? 0
        offset = try container.decode(Int.self, forKey: .offset)
        limit = try container.decode(Int.self, forKey: .limit)
        results = try container.decode([SearchResultRow].self, forKey: .results)
    }
}

struct SearchGroup: Identifiable {

    let username: String
    let results: [SearchResultRow]

    var id: String { username }
}

@MainActor
@Observable
final class SearchModel: Identifiable {

    /// Stable identity for the tab strip; two searches with the same term are
    /// still two tabs.
    let id = UUID()

    var client: EngineClient?
    var term = ""
    /// Inactive tabs keep their results but stop polling, so eight open
    /// searches cost one search worth of CPU.
    private(set) var isActive = true
    var token: Int?
    var results: [SearchResultRow] = []
    var total = 0
    var dropped = 0
    var isSearching = false
    var error = ""
    var selectedID: String?

    /// A search stays open after it is created: the network trickles results in
    /// for minutes, and the SSE stream tells us when a peer has answered.
    private(set) var isLive = false
    private(set) var startedAt = Date()
    private(set) var lastArrivalAt: Date?

    private(set) var needsRetry = false
    private var pollTask: Task<Void, Never>?
    private var refreshTask: Task<Void, Never>?

    var selected: SearchResultRow? {
        results.first { $0.id == selectedID }
    }

    /// A tab nobody has used yet: the next Return runs here instead of opening
    /// yet another tab.
    var isEmptyTab: Bool {
        token == nil && results.isEmpty && !isSearching
    }

    var title: String {
        let trimmed = term.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "New search" : trimmed
    }

    func setActive(_ active: Bool) {

        guard active != isActive else { return }

        isActive = active

        if active {
            if isLive {
                Task { await refresh() }
                startPolling()
            }

        } else {
            pollTask?.cancel()
            pollTask = nil
            refreshTask?.cancel()
            refreshTask = nil
        }
    }

    /// Closing a tab: drop the engine-side results and everything held here.
    func discard() async {

        cancel()

        if let client, let token {
            try? await client.deleteSearch(token: token)
        }

        token = nil
        results = []
        total = 0
        dropped = 0
        selectedID = nil
    }

    /// "50,000+" when the engine hit its cap, plain "1,240" otherwise.
    var totalLabel: String {
        let number = total.formatted()

        return dropped > 0 ? number + "+" : number
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

        await stop()

        isSearching = true
        error = ""
        results = []
        total = 0
        selectedID = nil
        startedAt = Date()
        lastArrivalAt = nil

        do {
            let summary = try await client.startSearch(term: query)
            token = summary.token
            isLive = true

            await refresh()
            startPolling()

        } catch {
            if let engineError = error as? EngineError, engineError.isNotLoggedIn {
                needsRetry = true
                self.error = "Soulseek is offline. This search runs by itself when the connection returns."
            } else {
                self.error = error.localizedDescription
            }

            isSearching = false
        }
    }

    /// Called when Soulseek comes back: a search entered while offline runs now.
    func retryIfNeeded() async {

        guard needsRetry, !term.trimmingCharacters(in: .whitespaces).isEmpty else { return }

        needsRetry = false
        await run()
    }

    /// Called from the event stream: a peer just answered. Refresh soon, but not
    /// once per event — a busy search fires many.
    func noteArrival(total: Int) {

        lastArrivalAt = Date()

        // A background tab keeps its old window; it refreshes when activated.
        if isActive && total > self.total {
            scheduleRefresh()
        }
    }

    func refresh() async {

        guard let client, let token else { return }

        guard let page = try? await client.searchResults(token: token, offset: 0, limit: 2_000) else {
            return
        }

        results = page.results
        total = page.total
        dropped = page.dropped
        isSearching = false

        if selectedID == nil {
            selectedID = results.first?.id
        }
    }

    /// The engine removed the search (or another client stopped it).
    func clearLive() {

        isLive = false
        isSearching = false
        pollTask?.cancel()
        refreshTask?.cancel()
    }

    /// Shutdown path: stop local work without another round trip.
    func cancel() {

        pollTask?.cancel()
        refreshTask?.cancel()
        isLive = false
        isSearching = false
    }

    func stop() async {

        pollTask?.cancel()
        pollTask = nil
        refreshTask?.cancel()
        refreshTask = nil

        if let client, let token {
            try? await client.stopSearch(token: token)
        }

        token = nil
        isLive = false
        isSearching = false
    }

    private func startPolling() {

        pollTask?.cancel()

        pollTask = Task { [weak self] in

            // A fallback for a dropped event stream; slow enough to be cheap.
            for _ in 0..<240 {
                try? await Task.sleep(nanoseconds: 2_000_000_000)

                guard let self, self.isLive else { return }
                await self.refresh()
            }
        }
    }

    private func scheduleRefresh() {

        refreshTask?.cancel()

        refreshTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 400_000_000)

            guard let self else { return }
            await self.refresh()
        }
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
    var kind = "sample"
    var allTracks: [CrateTrack] = []
    var selectedID: String?
    var error = ""
    var isLoading = false

    var tracks: [CrateTrack] {
        allTracks.filter { $0.kind == kind }
    }

    var selected: CrateTrack? {
        tracks.first { $0.id == selectedID }
    }

    func select(kind: String) {
        self.kind = kind
        selectedID = tracks.first?.id
    }

    func load() async {

        guard let client else { return }

        isLoading = true

        do {
            let page = try await client.crate()
            allTracks = page.tracks

            if selectedID == nil || !tracks.contains(where: { $0.id == selectedID }) {
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

    func remove(id: String) async {
        guard let client else { return }
        try? await client.deleteCrateTrack(id: id)
        await load()
    }

    func move(id: String, to kind: String) async {
        guard let client else { return }
        try? await client.setCrateKind(id: id, kind: kind)
        await load()
    }
}
