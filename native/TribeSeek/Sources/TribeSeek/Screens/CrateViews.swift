// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

struct CrateColumn: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 4) {
                ForEach(["sample", "dj"], id: \.self) { kind in
                    Button(kind == "sample" ? "Sample" : "DJ") {
                        model.crate.select(kind: kind)
                    }
                    .buttonStyle(ShelfChipStyle(isOn: model.crate.kind == kind))
                    .amberFocus(3)
                }

                Spacer()

                Text("\(model.crate.tracks.count)")
                    .font(Theme.mono(9))
                    .foregroundStyle(Theme.textMuted)

                Button {
                    Task { await model.crate.load() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10, weight: .medium))
                }
                .buttonStyle(DigIconKeyStyle(diameter: 24))
                .amberFocus(12)
                .help("Reload the crates")
            }
            .padding(.horizontal, 12)
            .frame(height: 44)

            Divider().overlay(Theme.border)

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(model.crate.tracks) { track in
                        CrateRowView(
                            track: track,
                            isSelected: model.crate.selectedID == track.id
                        ) {
                            model.crate.selectedID = track.id
                        }
                    }
                }
            }

            if model.crate.tracks.isEmpty {
                VStack(spacing: 6) {
                    Text(model.crate.kind == "dj" ? "No DJ crate yet" : "No sample crate yet")
                        .font(Theme.sans(12, .medium))
                        .foregroundStyle(Theme.textSecondary)
                    Text(model.crate.kind == "dj"
                         ? "Keep a track for your sets, or move one over from the sample crate."
                         : "Keep an audition and it lands here while it downloads.")
                        .font(Theme.sans(10))
                        .foregroundStyle(Theme.textMuted)
                        .multilineTextAlignment(.center)
                }
                .padding(20)
                .frame(maxWidth: .infinity)
            }
        }
        .background(Theme.bgCanvas)
    }
}

struct CrateRowView: View {

    let track: CrateTrack
    let isSelected: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(track.filename)
                        .font(Theme.sans(12, .medium))
                        .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                        .lineLimit(1)

                    InstrumentLabel(text: track.username)
                }

                Spacer(minLength: 6)

                HStack(spacing: 3) {
                    ForEach(0..<max(sortedStems.count, 1), id: \.self) { index in
                        LED(isOn: index < sortedStems.count,
                            color: index < sortedStems.count ? Theme.statusSaved : Color(hex: 0x2F3335),
                            size: 3.5)
                    }
                }

                StatusChip(text: track.status, color: statusColor)
            }
            .padding(.horizontal, 12)
            .frame(height: 52)
            .background(isSelected ? Theme.bgRowSelected : (hover ? Theme.bgHover : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }

    private var sortedStems: [String] {
        track.stems.keys.sorted()
    }

    private var statusColor: Color {
        switch track.status {
        case "ready", "scheduled", "downloaded": Theme.statusSaved
        case "failed": Theme.statusError
        case "separating", "downloading": Theme.accent
        default: Theme.textTertiary
        }
    }
}

struct CrateDetail: View {

    @Bindable var model: AppModel

    var body: some View {
        if let track = model.crate.selected {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(track.filename)
                        .font(Theme.sans(18, .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        InstrumentLabel(text: track.username)
                        StatusChip(text: track.status, color: statusColor(track.status))

                        if let bpm = track.bpm, bpm > 0 {
                            Text(String(format: "%.1f BPM", bpm))
                                .font(Theme.monoStrong(10))
                                .tracking(0.6)
                                .foregroundStyle(Theme.textTertiary)
                        }
                    }

                    if let error = track.error, !error.isEmpty {
                        Text(error)
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.statusError)
                    }

                    HStack(spacing: 8) {
                        Button {
                            Task { await model.crate.separate(id: track.id) }
                        } label: {
                            Label("Separate now", systemImage: "scissors")
                        }
                        .buttonStyle(DigPrimaryKeyStyle())
                        .amberFocus()

                        Button(track.kind == "dj" ? "Move to Sample" : "Move to DJ") {
                            Task {
                                await model.crate.move(
                                    id: track.id,
                                    to: track.kind == "dj" ? "sample" : "dj"
                                )
                            }
                        }
                        .buttonStyle(DigKeyStyle())
                        .amberFocus()

                        Button("Delete") {
                            Task { await model.crate.remove(id: track.id) }
                        }
                        .buttonStyle(DigKeyStyle())
                        .amberFocus()

                        if let path = track.alsPath, !path.isEmpty {
                            Button("Open in Live") {
                                NSWorkspace.shared.open(URL(fileURLWithPath: path))
                            }
                            .buttonStyle(DigKeyStyle())
                            .amberFocus()

                            Button("Reveal") {
                                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
                            }
                            .buttonStyle(DigKeyStyle())
                        }
                    }

                    if !track.stems.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            InstrumentLabel(text: "STEMS")

                            ForEach(track.stems.keys.sorted(), id: \.self) { name in
                                HStack(spacing: 10) {
                                    LED(isOn: true, color: Theme.statusSaved, size: 4)

                                    Text(name.uppercased())
                                        .font(Theme.mono(10))
                                        .tracking(1.0)
                                        .foregroundStyle(Theme.textSecondary)

                                    Spacer()

                                    if let path = track.stems[name] {
                                        Button("Reveal") {
                                            NSWorkspace.shared.activateFileViewerSelecting(
                                                [URL(fileURLWithPath: path)])
                                        }
                                        .buttonStyle(DigKeyStyle(dense: true))
                                    }
                                }
                                .padding(.horizontal, 10)
                                .frame(height: 30)
                                .background(WellSurface(
                                    radius: Theme.radiusPad,
                                    tint: Theme.statusSaved.opacity(0.04)
                                ))
                            }
                        }
                    }

                    if let local = track.localPath, !local.isEmpty {
                        Text(local)
                            .font(Theme.mono(10))
                            .foregroundStyle(Theme.textMuted)
                            .textSelection(.enabled)
                    }

                    Spacer()
                }
                .padding(24)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.bgWorkspace)

        } else {
            EmptyStatePane(
                symbol: "tray.full",
                title: "The crate",
                body: "Kept tracks appear here with their separation status, stems and the Live set the engine built."
            )
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "ready", "scheduled", "downloaded": Theme.statusSaved
        case "failed": Theme.statusError
        case "separating", "downloading": Theme.accent
        default: Theme.textTertiary
        }
    }
}
