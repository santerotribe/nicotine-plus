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

        case browse, search, audition, crate, live, settings

        var id: String { rawValue }

        var title: String {
            switch self {
            case .browse: "Browse"
            case .search: "Search"
            case .audition: "Audition"
            case .crate: "Crate"
            case .live: "Live"
            case .settings: "Digging"
            }
        }

        var symbol: String {
            switch self {
            case .browse: "square.stack"
            case .search: "magnifyingglass"
            case .audition: "waveform"
            case .crate: "tray.full"
            case .live: "music.note.list"
            case .settings: "slider.horizontal.3"
            }
        }
    }

    let supervisor = EngineSupervisor()
    let player = AuditionPlayer()

    var section: Section = .browse
    var state: EngineState?
    var statusText = ""
    var browse = BrowserModel()
    var audition = AuditionModel()
    var search = SearchModel()
    var crate = CrateModel()

    private var eventTask: Task<Void, Never>?
    private var loadedLocation = ""
    private var loadedSessionID = ""

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
        search.client = client
        crate.client = client

        if let snapshot = try? await client.state() {
            state = snapshot
            browse.adoptBrowsedUsers(snapshot.browsedUsers ?? [])
        }

        startEvents(client)

        if let target = ProcessInfo.processInfo.environment["DIG_OPEN"], !target.isEmpty {
            await browse(user: target)
        } else if let first = browse.users.first, browse.selectedUser == nil {
            await browse.select(user: first)
        }

        // A development aid: audition the first file so the transport and
        // waveform can be checked without clicking.
        if ProcessInfo.processInfo.environment["DIG_AUTO"] == "1",
           let folder = browse.selectedFolder,
           let file = browse.files.first,
           let user = browse.selectedUser {
            await audition(user: user, folder: folder, file: file)
        }
    }

    func shutdown() {
        eventTask?.cancel()
        supervisor.stop()
    }

    /// Section switches are cheap; only the crate needs a fetch on entry.
    func activateSection() async {
        if section == .crate {
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
                    NSLog("DigApp: event stream ended: %@", error.localizedDescription)
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

        case "audition":
            guard let snapshot = event.decode(AuditionState.self) else {
                NSLog("DigApp: audition event did not decode")
                return
            }

            guard snapshot.id == audition.sessionID else { return }
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
        await browse.browse(user: user)
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

        section = .audition
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

        audition.clear()
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
            await crate.load()

        } catch {
            audition.error = error.localizedDescription
        }
    }
}
