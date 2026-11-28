// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation
import Observation

/// The Rig screen's state: the engine's digging settings, loaded and patched
/// as a whole. Tokens are write-only; the engine only reports whether one is set.
@MainActor
@Observable
final class SettingsModel {

    var client: EngineClient?

    var workDir = ""
    var outputDir = ""
    var exportDir = ""
    var rolodexPath = ""
    var memberName = ""
    var renderer = "mvsep"
    var preset = "4"
    var mvsepSepType = ""
    var pcURL = ""
    var mvsepToken = ""
    var pcToken = ""
    var previewCacheMB = 2048
    var warpStems = true
    var openAfterBuild = true
    var warpMode = "complex"

    var presets: [String] = []
    var warpModes: [String] = []
    var readiness: [String: RendererReadiness] = [:]
    var mvsepTokenSet = false
    var pcTokenSet = false

    var isLoading = false
    var isSaving = false
    var error = ""
    var note = ""

    func load() async {

        guard let client else { return }

        isLoading = true

        do {
            adopt(try await client.settings())
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func save() async {

        guard let client else { return }

        isSaving = true
        error = ""
        note = ""

        let patch = SettingsPatch(
            workDir: workDir,
            outputDir: outputDir,
            exportDir: exportDir,
            rolodexPath: rolodexPath,
            memberName: memberName,
            renderer: renderer,
            preset: preset,
            mvsepSepType: mvsepSepType,
            pcURL: pcURL,
            previewCacheMB: previewCacheMB,
            warpStems: warpStems,
            openAfterBuild: openAfterBuild,
            warpMode: warpMode,
            mvsepToken: mvsepToken.isEmpty ? nil : mvsepToken,
            pcToken: pcToken.isEmpty ? nil : pcToken
        )

        do {
            adopt(try await client.updateSettings(patch))
            note = "Saved"
            mvsepToken = ""
            pcToken = ""
        } catch {
            self.error = error.localizedDescription
        }

        isSaving = false
    }

    private func adopt(_ payload: SettingsPayload) {

        workDir = payload.workDir
        outputDir = payload.outputDir
        exportDir = payload.exportDir
        rolodexPath = payload.rolodexPath
        memberName = payload.memberName
        renderer = payload.renderer
        preset = payload.preset
        mvsepSepType = payload.mvsepSepType
        pcURL = payload.pcURL
        previewCacheMB = payload.previewCacheMB
        warpStems = payload.warpStems
        openAfterBuild = payload.openAfterBuild
        warpMode = payload.warpMode
        presets = payload.presets
        warpModes = payload.warpModes
        readiness = payload.rendererAvailable
        mvsepTokenSet = payload.mvsepTokenSet
        pcTokenSet = payload.pcTokenSet
    }
}
