// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

/// One audition session, mirrored from `/audition` and the event stream.
@MainActor
@Observable
final class AuditionModel {

    var client: EngineClient?
    var sessionID: String?
    var state: AuditionState?
    var isStarting = false
    var error = ""
    var note = ""
    var keptTrackID = ""
    var keptStatus = ""

    private var refreshTask: Task<Void, Never>?

    var isKept: Bool { !keptTrackID.isEmpty }

    func begin(user: String, folder: String, file: SharedFileRow) {

        refreshTask?.cancel()
        sessionID = nil
        state = nil
        error = ""
        note = ""
        keptTrackID = ""
        keptStatus = ""
        isStarting = true
    }

    /// A light fallback for a dropped SSE connection: poll while nothing playable exists.
    func scheduleRefresh() {

        refreshTask?.cancel()

        refreshTask = Task { [weak self] in
            for _ in 0..<24 {
                try? await Task.sleep(nanoseconds: 1_500_000_000)

                guard let self, let client = self.client, let id = self.sessionID else { return }

                if let snapshot = try? await client.audition(id: id) {
                    self.state = snapshot

                    if snapshot.source != nil && snapshot.catalogueState != "pending" {
                        return
                    }
                }
            }
        }
    }

    func clear() {
        refreshTask?.cancel()
        sessionID = nil
        state = nil
        note = ""
        error = ""
    }
}
