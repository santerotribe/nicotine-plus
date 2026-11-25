// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

/// Finds the engine, or starts one.
///
/// The spike prefers a running engine (the GTK app already exposes one on 8766),
/// because two clients on the same Soulseek account fight over the login. When
/// nothing answers, it launches the Python engine headless as a child process,
/// exactly as the native client will.
@MainActor
@Observable
final class EngineSupervisor {

    enum Phase: Equatable {

        case idle
        case probing
        case launching
        case ready
        case failed(String)
    }

    private(set) var phase: Phase = .idle
    private(set) var message = "Looking for the engine…"
    private(set) var client: EngineClient?
    private(set) var engineVersion = ""

    private var process: Process?
    private var spawnedByUs = false
    private var watchdogTask: Task<Void, Never>?

    // MARK: - Configuration

    struct Config {

        var baseURL: URL
        var token: String
        var repoRoot: URL?
        var launchIfMissing: Bool
        var profileConfig: URL?
        var profileData: URL?

        static func fromEnvironment() -> Config {

            let environment = ProcessInfo.processInfo.environment
            let repo = environment["NICOTINE_REPO"].map { URL(fileURLWithPath: $0) }
                ?? BundleSearch.repoRoot()

            let baseURL = environment["NICOTINE_API_URL"].flatMap(URL.init(string:))
                ?? URL(string: "http://127.0.0.1:8766")!

            return Config(
                baseURL: baseURL,
                token: environment["NICOTINE_API_TOKEN"] ?? "devtoken",
                repoRoot: repo,
                launchIfMissing: environment["DIG_NO_LAUNCH"] != "1",
                profileConfig: repo?.appendingPathComponent(".dev/config"),
                profileData: repo?.appendingPathComponent(".dev/data")
            )
        }
    }

    // MARK: - Start

    func start() async {

        guard phase == .idle || isFailure else { return }

        let config = Config.fromEnvironment()
        phase = .probing
        message = "Looking for the engine…"

        let probe = EngineClient(baseURL: config.baseURL, token: config.token)

        if let health = try? await probe.health() {
            adopt(probe, version: health.version)
            return
        }

        guard config.launchIfMissing, let repo = config.repoRoot,
              let python = pythonExecutable(in: repo),
              let profileConfig = config.profileConfig,
              let profileData = config.profileData,
              FileManager.default.fileExists(atPath: profileConfig.path)
        else {
            phase = .failed("No engine on \(config.baseURL.absoluteString). Start it with: NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=devtoken .venv/bin/python -m pynicotine -n --config .dev/config --user-data .dev/data")
            message = "Engine not running"
            NSLog("DigApp: no engine and no launch path (repo=%{public}@)",
                  config.repoRoot?.path ?? "nil")
            return
        }

        phase = .launching
        message = "Starting the engine…"

        let port = config.baseURL.port ?? 8766
        let child = Process()
        child.executableURL = python
        child.arguments = [
            "-m", "pynicotine", "-n",
            "--config", profileConfig.path,
            "--user-data", profileData.path
        ]
        child.currentDirectoryURL = repo

        var environment = ProcessInfo.processInfo.environment
        environment["NICOTINE_API_PORT"] = String(port)
        environment["NICOTINE_API_TOKEN"] = config.token
        environment["GTK_A11Y"] = "none"
        let path = (environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin")
        environment["PATH"] = path + ":/opt/homebrew/bin:/usr/local/bin"
        child.environment = environment

        let logURL = Self.logURL()
        NSLog("DigApp: engine log at \(logURL.path)")

        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }

        if let handle = try? FileHandle(forWritingTo: logURL) {
            _ = try? handle.seekToEnd()
            child.standardOutput = handle
            child.standardError = handle
        }

        do {
            try child.run()
            process = child
            spawnedByUs = true

        } catch {
            phase = .failed("Could not start the engine: \(error.localizedDescription)")
            return
        }

        for _ in 0..<60 {
            try? await Task.sleep(nanoseconds: 400_000_000)

            if let health = try? await probe.health() {
                adopt(probe, version: health.version)
                return
            }

            if !child.isRunning {
                phase = .failed("The engine exited during startup. See \(logURL.path)")
                return
            }
        }

        phase = .failed("The engine did not answer within 24 seconds. See \(logURL.path)")
    }

    func stop() {

        watchdogTask?.cancel()
        watchdogTask = nil

        guard spawnedByUs, let process, process.isRunning else { return }

        process.terminate()
        self.process = nil
    }

    private func adopt(_ client: EngineClient, version: String) {

        self.client = client
        engineVersion = version
        phase = .ready
        message = "Engine \(version)"
        startWatchdog(client)
    }

    /// The engine can die under us (it runs an 8-hour share index in a separate
    /// process). Watch it, and bring a fresh one up if it stops answering.
    private func startWatchdog(_ client: EngineClient) {

        watchdogTask?.cancel()

        watchdogTask = Task { [weak self] in

            var failures = 0

            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5_000_000_000)

                guard let self else { return }

                if (try? await client.health()) != nil {
                    failures = 0
                    continue
                }

                failures += 1

                guard failures >= 3 else { continue }

                self.handleEngineLoss()
                return
            }
        }
    }

    private func handleEngineLoss() {

        client = nil
        phase = .failed("The engine stopped answering. Restarting…")
        message = "Engine lost"

        process = nil
        spawnedByUs = false

        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            await self?.start()
        }
    }

    private var isFailure: Bool {
        if case .failed = phase { return true }
        return false
    }

    // MARK: - Helpers

    /// `~/Library/Logs` first, the temp folder when the profile is restricted.
    private static func logURL() -> URL {

        let library = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/DigApp-engine.log")

        if FileManager.default.isWritableFile(atPath: library.deletingLastPathComponent().path) {
            return library
        }

        return FileManager.default.temporaryDirectory.appendingPathComponent("DigApp-engine.log")
    }

    private func pythonExecutable(in repo: URL) -> URL? {

        let venv = repo.appendingPathComponent(".venv/bin/python")

        if FileManager.default.isExecutableFile(atPath: venv.path) {
            return venv
        }

        return URL(fileURLWithPath: "/usr/bin/env")
    }
}

/// Walk up from the executable until the engine checkout is found.
enum BundleSearch {

    static func repoRoot() -> URL? {

        var candidates: [URL] = []

        if let env = ProcessInfo.processInfo.environment["NICOTINE_REPO"] {
            candidates.append(URL(fileURLWithPath: env))
        }

        // Walk up from both the working directory and the binary: the build
        // lives in /tmp, the checkout does not.
        for start in [
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
            URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        ] {
            var cursor = start

            for _ in 0..<12 {
                candidates.append(cursor)
                cursor.deleteLastPathComponent()
            }
        }

        for candidate in candidates {
            let marker = candidate.appendingPathComponent("pynicotine/engineapi/server.py")

            if FileManager.default.fileExists(atPath: marker.path) {
                return candidate
            }
        }

        return nil
    }
}
