// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation

/// A headless check of the client against a live engine.
///
/// `DIG_SELFTEST=1` runs it before the UI starts and exits with 0 on success,
/// so the spike can be verified without clicking anything.
enum SelfTest {

    static func run() async -> Bool {

        let config = EngineSupervisor.Config.fromEnvironment()
        let client = EngineClient(baseURL: config.baseURL, token: config.token)
        var failures = 0

        func check(_ name: String, _ condition: Bool, _ detail: String = "") {
            print((condition ? "PASS " : "FAIL ") + name + (detail.isEmpty ? "" : " — " + detail))
            if !condition { failures += 1 }
        }

        do {
            let health = try await client.health()
            check("health", health.ok, health.version)

            let state = try await client.state()
            check("state", state.username != nil, state.username ?? "not logged in")

            try await client.browse(user: "santero")

            var summary: BrowseSummary?

            for _ in 0..<20 {
                if let candidate = try? await client.summary(user: "santero"), candidate.files > 0 {
                    summary = candidate
                    break
                }

                try? await Task.sleep(nanoseconds: 500_000_000)
            }

            check("browse summary", summary != nil,
                  summary.map { "\($0.folders) folders, \($0.files) files" } ?? "no answer")

            let folders = try await client.folders(user: "santero", limit: 5)
            check("folder page", !folders.folders.isEmpty, "\(folders.total) total")

            guard let folder = folders.folders.keys.first else {
                return failures == 0
            }

            let files = try await client.files(user: "santero", folder: folder, limit: 5)
            check("file page", !files.files.isEmpty, "\(files.total) in \(folder)")

            guard let file = files.files.first else {
                return failures == 0
            }

            let audition = try await client.startAudition(.init(
                username: "santero",
                virtualPath: VirtualPath.join(folder: folder, name: file.name),
                size: file.size,
                duration: Double(file.length ?? 0),
                attributes: .init(bitrate: file.bitrate, length: file.length, vbr: file.vbr,
                                  sampleRate: file.sampleRate, bitDepth: file.bitDepth)
            ))

            check("audition started", !audition.id.isEmpty, audition.id)

            var resolved: AuditionState?

            for _ in 0..<20 {
                let snapshot = try await client.audition(id: audition.id)

                if snapshot.source != nil {
                    resolved = snapshot
                    break
                }

                try? await Task.sleep(nanoseconds: 400_000_000)
            }

            check("audition source", resolved?.source != nil,
                  resolved?.source?.kind.rawValue ?? "unresolved")

            if let location = resolved?.source?.playableLocation {
                let exists = FileManager.default.fileExists(atPath: location)
                check("source is playable", exists || location.hasPrefix("http"), location)
            }

            try await client.closeAudition(id: audition.id)
            check("audition closed", true)

        } catch {
            check("engine reached", false, String(describing: error))
        }

        if failures == 0 {
            print("ALL PASS")
        } else {
            print("\(failures) FAILURE(S)")
        }

        return failures == 0
    }
}
