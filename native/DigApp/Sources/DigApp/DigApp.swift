// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

@main
struct DigApp: App {

    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup("Digging") {
            AppShell(model: model)
                .frame(minWidth: 1_180, minHeight: 740)
                .background(Theme.bgCanvas)
                .task {
                    if ProcessInfo.processInfo.environment["DIG_SELFTEST"] == "1" {
                        let passed = await SelfTest.run()
                        exit(passed ? 0 : 1)
                    }

                    await model.start()
                }
                .onDisappear { model.shutdown() }
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1_380, height: 880)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {

    func applicationDidFinishLaunching(_ notification: Notification) {
        Theme.registerFonts()
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        ChildProcessRegistry.terminateAll()
    }
}

/// Child engines this app started; an orphan would keep the Soulseek session open.
enum ChildProcessRegistry {

    private static let lock = NSLock()
    private static var processes: [Process] = []

    static func add(_ process: Process) {
        lock.lock()
        processes.append(process)
        lock.unlock()
    }

    static func remove(_ process: Process) {
        lock.lock()
        processes.removeAll { $0 === process }
        lock.unlock()
    }

    static func terminateAll() {
        lock.lock()
        let running = processes
        processes.removeAll()
        lock.unlock()

        for process in running where process.isRunning {
            process.terminate()
        }
    }
}
