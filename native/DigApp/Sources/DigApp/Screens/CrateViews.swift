// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

struct CrateColumn: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                InstrumentLabel(text: "KEPT TRACKS")
                Spacer()
                Button("Reload") {
                    Task { await model.crate.load() }
                }
                .buttonStyle(DigKeyStyle(dense: true))
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
                    Text("Nothing kept yet")
                        .font(Theme.sans(12, .medium))
                        .foregroundStyle(Theme.textSecondary)
                    Text("Keep an audition and it lands here while it downloads.")
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

                        if let bpm = track.bpm {
                            InstrumentLabel(text: String(format: "%.1f BPM", bpm))
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

                        if let path = track.alsPath, !path.isEmpty {
                            Button("Open in Live") {
                                NSWorkspace.shared.open(URL(fileURLWithPath: path))
                            }
                            .buttonStyle(DigKeyStyle())

                            Button("Reveal") {
                                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
                            }
                            .buttonStyle(DigKeyStyle())
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
