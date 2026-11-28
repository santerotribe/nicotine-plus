// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

/// The Rig: everything the engine needs to know, in one place.
struct RigScreen: View {

    @Bindable var settings: SettingsModel

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Theme.border)

            ScrollView {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)],
                    spacing: 12
                ) {
                    collective
                    separation
                    output
                    cache
                }
                .padding(14)
            }
        }
        .background(Theme.bgWorkspace)
        .task { await settings.load() }
    }

    private var header: some View {

        HStack(spacing: 10) {
            InstrumentLabel(text: "RIG")

            if !settings.note.isEmpty {
                Text(settings.note)
                    .font(Theme.mono(8.5))
                    .foregroundStyle(Theme.statusSaved)
            }

            if !settings.error.isEmpty {
                Text(settings.error)
                    .font(Theme.mono(8.5))
                    .foregroundStyle(Theme.statusError)
                    .lineLimit(1)
            }

            Spacer()

            Button {
                Task { await settings.save() }
            } label: {
                Label("Save", systemImage: "checkmark")
            }
            .buttonStyle(DigPrimaryKeyStyle())
            .disabled(settings.isSaving)
            .amberFocus()
        }
        .padding(.horizontal, 14)
        .frame(height: 48)
        .background(Theme.bgBase)
    }

    private var collective: some View {

        RigCard("COLLECTIVE") {
            RigField(label: "Member name", text: $settings.memberName,
                     placeholder: "who found it")

            RigField(label: "Ledger path", text: $settings.rolodexPath,
                     placeholder: "~/Documents/Tribe Seek/rolodex.json")

            Text("Point the ledger at a synced folder to share it with the crew.")
                .font(Theme.sans(10))
                .foregroundStyle(Theme.textMuted)

            Button("Reveal ledger") {
                NSWorkspace.shared.activateFileViewerSelecting(
                    [URL(fileURLWithPath: settings.rolodexPath)]
                )
            }
            .buttonStyle(DigKeyStyle(dense: true))
        }
    }

    private var separation: some View {

        RigCard("SEPARATION") {
            HStack(spacing: 4) {
                ForEach(["mvsep", "pc", "local"], id: \.self) { renderer in
                    Button(renderer.uppercased()) {
                        settings.renderer = renderer
                    }
                    .buttonStyle(ShelfChipStyle(isOn: settings.renderer == renderer))
                    .amberFocus(3)
                }

                Spacer()
            }

            if let readiness = settings.readiness[settings.renderer] {
                HStack(spacing: 5) {
                    LED(isOn: readiness.ready,
                        color: readiness.ready ? Theme.statusSaved : Theme.statusError,
                        size: 4)

                    Text(readiness.ready ? "READY" : readiness.message)
                        .font(Theme.mono(8.5))
                        .foregroundStyle(readiness.ready ? Theme.statusSaved : Theme.textMuted)
                        .lineLimit(2)
                }
            }

            if settings.renderer == "mvsep" {
                RigField(label: "MVSEP token",
                         text: $settings.mvsepToken,
                         secure: true,
                         placeholder: settings.mvsepTokenSet ? "•••••• set" : "paste token")

                RigField(label: "Separation type", text: $settings.mvsepSepType,
                         placeholder: "render id")
            }

            if settings.renderer == "pc" {
                RigField(label: "Studio PC URL", text: $settings.pcURL,
                         placeholder: "http://studio:8765")

                RigField(label: "Studio PC token", text: $settings.pcToken,
                         secure: true,
                         placeholder: settings.pcTokenSet ? "•••••• set" : "token")
            }

            HStack(spacing: 4) {
                Text("PRESET")
                    .font(Theme.mono(7.5))
                    .foregroundStyle(Theme.textMuted)

                ForEach(settings.presets, id: \.self) { preset in
                    Button("\(preset) STEMS") {
                        settings.preset = preset
                    }
                    .buttonStyle(ShelfChipStyle(isOn: settings.preset == preset))
                    .amberFocus(3)
                }

                Spacer()
            }
        }
    }

    private var output: some View {

        RigCard("OUTPUT & LIVE") {
            RigField(label: "Working folder", text: $settings.workDir,
                     placeholder: "downloads, stems, crate")

            RigField(label: "Sets folder", text: $settings.outputDir,
                     placeholder: "generated Live sets")

            RigField(label: "Export folder", text: $settings.exportDir,
                     placeholder: "blank = Ableton User Library")

            HStack(spacing: 6) {
                Text("WARP")
                    .font(Theme.mono(7.5))
                    .foregroundStyle(Theme.textMuted)

                Picker("Warp", selection: $settings.warpMode) {
                    ForEach(settings.warpModes, id: \.self) { mode in
                        Text(mode.uppercased()).tag(mode)
                    }
                }
                .labelsHidden()
                .frame(width: 130)

                Spacer()
            }

            Toggle("Warp stems to the set tempo", isOn: $settings.warpStems)
                .toggleStyle(.switch)
                .font(Theme.sans(11))
                .foregroundStyle(Theme.textSecondary)

            Toggle("Open the set when it is built", isOn: $settings.openAfterBuild)
                .toggleStyle(.switch)
                .font(Theme.sans(11))
                .foregroundStyle(Theme.textSecondary)
        }
    }

    private var cache: some View {

        RigCard("CACHE") {
            HStack(spacing: 8) {
                Text("PREVIEW BUDGET")
                    .font(Theme.mono(7.5))
                    .foregroundStyle(Theme.textMuted)

                TextField("2048", value: $settings.previewCacheMB, format: .number)
                    .textFieldStyle(.plain)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.trailing)
                    .padding(.horizontal, 8)
                    .frame(width: 90, height: 26)
                    .background(WellSurface(radius: Theme.radiusPad))

                Text("MB")
                    .font(Theme.mono(9))
                    .foregroundStyle(Theme.textMuted)

                Spacer()
            }

            Text("Previews and exports are disposable; the crate and stems are not.")
                .font(Theme.sans(10))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Pieces

struct RigCard<Content: View>: View {

    let title: String
    let content: Content

    init(_ title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            InstrumentLabel(text: title)
            content
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgCard))
        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.border, lineWidth: 1))
    }
}

struct RigField: View {

    let label: String
    @Binding var text: String
    var secure = false
    var placeholder = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            InstrumentLabel(text: label)

            Group {
                if secure {
                    SecureField(placeholder, text: $text)
                } else {
                    TextField(placeholder, text: $text)
                }
            }
            .textFieldStyle(.plain)
            .font(Theme.mono(11))
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 8)
            .frame(height: 28)
            .background(WellSurface(radius: Theme.radiusPad))
        }
    }
}
