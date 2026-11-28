// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

/// The app's one source of truth: engine connection, browse state, the current
/// audition and the audio player that follows it.
@MainActor
@Observable
final class AppModel {

    enum Section: String, CaseIterable, Identifiable {

        // One workspace: search and shelf are ways of looking at the network,
        // crates and the rolodex are what you keep, the rig configures it all.
        case search, shelf, crates, rolodex, rig

        var id: String { rawValue }

        var title: String {
            switch self {
            case .search: "Search"
            case .shelf: "Shelf"
            case .crates: "Crates"
            case .rolodex: "Rolodex"
            case .rig: "Rig"
            }
        }

        var symbol: String {
            switch self {
            case .search: "magnifyingglass"
            case .shelf: "square.stack.3d.up"
            case .crates: "tray.full"
            case .rolodex: "person.2"
            case .rig: "slider.horizontal.3"
            }
        }
    }

    let supervisor = EngineSupervisor()
    let player = AuditionPlayer()

    var section: Section = .search
    /// The expanded audition tray: the old Audition tab, folded into the shell.
    var trayExpanded = false
    var state: EngineState?
    var statusText = ""
    /// True when the last disconnect was the server kicking us for another
    /// login on the same account; retrying automatically would just ping-pong.
    var accountInUse = false
    var browse = BrowserModel()
    var audition = AuditionModel()
    /// The tab on screen. Every open search is a SearchModel; closing a tab
    /// discards its engine-side store, so eight tabs do not mean eight searches
    /// worth of memory.
    var search: SearchModel
    var searchTabs: [SearchModel]
    /// What is typed in the top bar, kept apart from the active tab's term so
    /// a new query opens a tab instead of overwriting the one being read.
    var searchDraft = ""
    var crate = CrateModel()

    private var eventTask: Task<Void, Never>?
    private var stemTask: Task<Void, Never>?
    private var loadedLocation = ""
    private var loadedSessionID = ""

    private static let maxSearchTabs = 8

    init() {
        let first = SearchModel()
        search = first
        searchTabs = [first]
    }

    var client: EngineClient? { supervisor.client }
    var isConnected: Bool { supervisor.phase == .ready && client != nil }

    // MARK: - Lifecycle

    func start() async {

        await supervisor.start()

        guard let client else {
            statusText = supervisor.message
            return
        }

        statusText = supervisor.message
        browse.client = client
        audition.client = client
        crate.client = client
        for tab in searchTabs {
            tab.client = client
        }

        if let snapshot = try? await client.state() {
            state = snapshot
            browse.adoptBrowsedUsers(snapshot.browsedUsers ?? [])
        }

        startEvents(client)

        // The app opens on Search. A shelf is entered deliberately, from a
        // result or from TRIBE_OPEN=<user>.
        if let target = ProcessInfo.processInfo.environment["TRIBE_OPEN"], !target.isEmpty {
            await browse(user: target)
        }

        // A development aid: run a search on launch, so the results list can be
        // checked without typing.
        if let term = ProcessInfo.processInfo.environment["TRIBE_SEARCH"], !term.isEmpty {
            searchDraft = term
            await submitSearch()
        }

        if ProcessInfo.processInfo.environment["TRIBE_BINS"] == "1" {
            browse.binGrid = true
        }

        // A development aid: open a shelf at one folder, for the dig path.
        if let raw = ProcessInfo.processInfo.environment["TRIBE_DIG"],
           let split = raw.firstIndex(of: "|") {
            let user = String(raw[raw.startIndex..<split])
            let folder = String(raw[raw.index(after: split)...])
            await dig(user: user, folder: folder)
        }

        // A development aid: audition the first file so the deck and waveform
        // can be checked without clicking. Falls back to the first search hit,
        // so a launch with TRIBE_SEARCH and TRIBE_AUTO lands on a live deck.
        if ProcessInfo.processInfo.environment["TRIBE_AUTO"] == "1" {

            if let folder = browse.selectedFolder,
               let file = browse.files.first,
               let user = browse.selectedUser {
                await audition(user: user, folder: folder, file: file)

            } else {
                // Search results trickle in after the first page: give the
                // network a few seconds before auditioning the first hit.
                let playable = ["mp3", "flac", "wav", "aif", "aiff", "m4a", "ogg", "opus"]

                for _ in 0..<20 {
                    if let result = search.results.first(where: {
                        playable.contains(($0.filename as NSString).pathExtension.lowercased())
                    }) {
                        await audition(user: result.username,
                                       folder: result.folder,
                                       file: result.asFile)
                        break
                    }

                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
        }
    }

    /// Login and disconnect events only say what changed; re-read the snapshot
    /// so the status light and the account row follow the real connection.
    func refreshState() async {

        guard let client else { return }

        if let snapshot = try? await client.state() {
            state = snapshot
        }
    }

    var isOnline: Bool { state?.connection == .online }

    /// Log in again, then let a search that was waiting run.
    func reconnect() async {

        guard let client else { return }

        try? await client.reconnect()

        for _ in 0..<30 {
            try? await Task.sleep(nanoseconds: 1_000_000_000)

            await refreshState()

            if isOnline {
                break
            }
        }

        for tab in searchTabs {
            await tab.retryIfNeeded()
        }
    }

    func shutdown() {
        eventTask?.cancel()
        stemTask?.cancel()
        for tab in searchTabs {
            tab.cancel()
        }
        browse.commitSeen()
        supervisor.stop()
    }

    /// Section switches are cheap; only the crate needs a fetch on entry.
    func activateSection() async {
        if section == .crates {
            await crate.load()
        }
    }

    // MARK: - Events

    private func startEvents(_ client: EngineClient) {

        eventTask?.cancel()

        eventTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    for try await event in client.events() {
                        await self?.handle(event)
                    }
                } catch {
                    NSLog("TribeSeek: event stream ended: %@", error.localizedDescription)
                }

                try? await Task.sleep(nanoseconds: 1_500_000_000)
            }
        }
    }

    private func handle(_ event: EngineEvent) async {

        switch event.type {
        case "browse":
            struct Payload: Decodable {
                let username: String
                let done: Bool
                let files: Int
                let folders: Int
            }

            guard let payload = event.decode(Payload.self) else { return }

            // A browse may have been started from another client: adopt the peer
            // so the list reflects the engine, not just this window.
            if !browse.users.contains(payload.username) {
                browse.users.insert(payload.username, at: 0)
            }

            guard payload.done else { return }

            if browse.selectedUser == nil {
                await browse.select(user: payload.username)
                return
            }

            guard payload.username == browse.selectedUser else { return }
            await browse.reloadCurrent()

        case "login":
            struct LoginEvent: Decodable { let success: Bool; let username: String? }

            if let login = event.decode(LoginEvent.self), login.success {
                accountInUse = false
                await refreshState()
                await search.retryIfNeeded()
            }

        case "disconnect":
            struct DisconnectEvent: Decodable { let relogged: Bool? }
            accountInUse = event.decode(DisconnectEvent.self)?.relogged ?? false
            await refreshState()

        case "search":
            struct SearchArrival: Decodable {
                let token: Int
                let total: Int
                let user: String
            }

            if let arrival = event.decode(SearchArrival.self),
               let tab = searchTabs.first(where: { $0.token == arrival.token }) {
                tab.noteArrival(total: arrival.total)
            }

        case "search_removed":
            struct Removed: Decodable { let token: Int }
            if let removed = event.decode(Removed.self),
               let tab = searchTabs.first(where: { $0.token == removed.token }) {
                tab.clearLive()
            }

        case "audition":
            guard let snapshot = event.decode(AuditionState.self) else {
                NSLog("TribeSeek: audition event did not decode")
                return
            }

            guard snapshot.id == audition.sessionID else { return }

            // A session started outside this window (API, CLI) still deserves
            // the deck; only the first snapshot opens it, so collapsing sticks.
            if audition.state == nil {
                trayExpanded = true
            }

            apply(snapshot)

        case "audition_closed":
            struct Payload: Decodable { let id: String }
            guard let payload = event.decode(Payload.self), payload.id == audition.sessionID else { return }
            audition.state = nil

        case "crate":
            struct Payload: Decodable {
                let trackId: String
                let status: String
                let error: String?
            }
            guard let payload = event.decode(Payload.self),
                  payload.trackId == audition.keptTrackID else { return }
            audition.keptStatus = payload.status

        default:
            break
        }
    }

    /// The engine told us where the audio is; keep the player on the best source
    /// and never restart it for the same location.
    func apply(_ snapshot: AuditionState) {

        audition.state = snapshot
        audition.isStarting = false

        guard let source = snapshot.source, let location = source.playableLocation else {
            if snapshot.peer.error.isEmpty == false {
                audition.note = snapshot.peer.error
            }
            return
        }

        let isNewSession = snapshot.id != loadedSessionID

        if isNewSession {
            loadedSessionID = snapshot.id
            loadedLocation = ""
            player.stop()
        }

        guard location != loadedLocation else { return }

        let resumeAt = isNewSession ? 0 : player.position()
        loadedLocation = location

        player.load(
            location: location,
            title: snapshot.filename,
            badge: badge(for: snapshot, source: source),
            startAt: resumeAt
        )
    }

    private func badge(for snapshot: AuditionState, source: AuditionSource) -> String {
        switch source.kind {
        case .local: "LOCAL"
        case .peer: source.complete ? "PEER · FILE" : "PEER · PARTIAL"
        case .catalogue: "CATALOGUE · " + (snapshot.catalogue.first?.source.uppercased() ?? "STREAM")
        }
    }

    // MARK: - Actions

    func browse(user: String) async {

        guard client != nil else { return }

        browse.users.insert(user, at: 0)
        browse.selectedUser = user
        section = .shelf
        await browse.browse(user: user)
    }

    /// Open a peer's shelf at one of their folders. The search result already
    /// carries both, so this is the whole "dig into this record" gesture.
    func dig(user: String, folder: String) async {

        guard client != nil else { return }

        // A dig from a cold launch can arrive while Soulseek is still logging
        // in; the browse would be dropped and the shelf would stay empty.
        for _ in 0..<40 {
            if isOnline { break }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }

        section = .shelf

        if browse.selectedUser == user, !browse.folders.isEmpty {
            await browse.focus(folder: folder)
            return
        }

        await browse(user: user)

        // A slow or offline peer leaves its own error in place; do not mask it
        // with a folder mismatch.
        guard !browse.folders.isEmpty else { return }

        await browse.focus(folder: folder)
    }

    // MARK: - Search tabs

    /// Return in the top bar. An unused tab runs in place; anything else opens
    /// a new tab, so the results being read stay where they are.
    func submitSearch() async {

        let term = searchDraft.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !term.isEmpty else { return }

        if search.isEmptyTab {
            search.term = term
            await search.run()
            return
        }

        if search.term.trimmingCharacters(in: .whitespacesAndNewlines) == term {
            return
        }

        await openSearch(term: term)
    }

    func openSearch(term: String) async {

        let tab = SearchModel()
        tab.client = client
        tab.term = term

        search.setActive(false)
        searchTabs.append(tab)
        search = tab
        searchDraft = term
        section = .search

        trimSearchTabs()
        await tab.run()
    }

    /// The plus key reuses an empty tab when one is already sitting there.
    func newBlankSearch() {

        if let blank = searchTabs.first(where: { $0 !== search && $0.isEmptyTab }) {
            activate(blank)
            return
        }

        let tab = SearchModel()
        tab.client = client

        search.setActive(false)
        searchTabs.append(tab)
        search = tab
        searchDraft = ""
        section = .search

        trimSearchTabs()
    }

    func activate(_ tab: SearchModel) {

        guard tab !== search else { return }

        search.setActive(false)
        search = tab
        tab.setActive(true)
        searchDraft = tab.term
        section = .search
    }

    func closeSearch(_ tab: SearchModel) async {

        await tab.discard()
        searchTabs.removeAll { $0 === tab }

        if searchTabs.isEmpty {
            let fresh = SearchModel()
            fresh.client = client
            searchTabs = [fresh]
            search = fresh
            searchDraft = ""
            return
        }

        if tab === search, let next = searchTabs.last {
            search = next
            next.setActive(true)
            searchDraft = next.term
        }
    }

    /// Close the oldest inactive tab once the strip passes its cap.
    private func trimSearchTabs() {

        while searchTabs.count > Self.maxSearchTabs {
            guard let victim = searchTabs.first(where: { $0 !== search }) else { break }

            searchTabs.removeAll { $0 === victim }
            victim.cancel()

            if let client, let token = victim.token {
                Task { try? await client.deleteSearch(token: token) }
            }
        }
    }

    func audition(user: String, folder: String, file: SharedFileRow) async {

        guard let client else { return }

        // One live session per window: the previous preview is paused and swept
        // instead of piling up transfers on the engine.
        if let previous = audition.sessionID {
            try? await client.closeAudition(id: previous)
            player.stop()
            loadedSessionID = ""
            loadedLocation = ""
        }

        // Auditioning never steals the screen: the tray opens where you are.
        trayExpanded = true
        audition.begin(user: user, folder: folder, file: file)

        do {
            let snapshot = try await client.startAudition(.init(
                username: user,
                virtualPath: folder.isEmpty ? file.name : folder + "\\" + file.name,
                size: file.size,
                duration: Double(file.length ?? 0),
                attributes: .init(
                    bitrate: file.bitrate,
                    length: file.length,
                    vbr: file.vbr,
                    sampleRate: file.sampleRate,
                    bitDepth: file.bitDepth
                )
            ))

            audition.sessionID = snapshot.id
            apply(snapshot)
            audition.scheduleRefresh()

        } catch {
            audition.error = error.localizedDescription
        }
    }

    /// End the server-side session too, so the preview transfer is paused and
    /// the cache sweep can clean the file up.
    func closeAudition() async {

        if let client, let id = audition.sessionID {
            try? await client.closeAudition(id: id)
        }

        stemTask?.cancel()
        audition.clear()
        trayExpanded = false
        player.stop()
        loadedSessionID = ""
        loadedLocation = ""
    }

    func keep() async {

        guard let client, let id = audition.sessionID else { return }

        do {
            let track = try await client.keepAudition(id: id)
            audition.keptTrackID = track.id
            audition.keptStatus = track.status
            audition.note = "Kept — separating when the download lands"
            audition.isSeparating = true
            await crate.load()
            watchStems(trackID: track.id)

        } catch {
            audition.error = error.localizedDescription
        }
    }

    /// Stems arrive after the download and the separation run; watch the crate
    /// until they exist instead of making the user refresh.
    private func watchStems(trackID: String) {

        stemTask?.cancel()
        stemTask = Task { [weak self] in

            for _ in 0..<120 {
                try? await Task.sleep(nanoseconds: 3_000_000_000)

                guard let self, let client = self.client else { return }

                guard let page = try? await client.crate(),
                      let track = page.tracks.first(where: { $0.id == trackID }) else {
                    continue
                }

                self.audition.keptStatus = track.status
                self.audition.isSeparating = track.stems.isEmpty
                self.audition.stems = track.stems
                    .map { StemFile(name: $0.key, path: $0.value) }
                    .sorted { $0.name < $1.name }

                if !track.stems.isEmpty || track.status == "failed" {
                    return
                }
            }
        }
    }
}
