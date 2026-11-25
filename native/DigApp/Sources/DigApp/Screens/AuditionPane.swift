// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

/// The listening surface: what is playing, where it came from, and what the
/// engine is still fetching.
struct AuditionPane: View {

    @Bindable var model: AppModel
    var compact = false

    @State private var isHoveringArtwork = false

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1.0 / 30.0)) { _ in
            let position = model.player.position()

            Group {
                if let state = model.audition.state {
                    content(state: state, position: position)
                } else if model.audition.isStarting || !model.audition.error.isEmpty {
                    loading
                } else {
                    EmptyStatePane(
                        symbol: "waveform",
                        title: "Nothing auditioning",
                        body: "Press Enter on a file in Browse or Search. The engine starts the peer fetch and the catalogue lookup together; playback follows whichever is ready first."
                    )
                }
            }
        }
        .background(Theme.bgWorkspace)
    }

    private var loading: some View {

        VStack(spacing: 10) {
            if model.audition.error.isEmpty {
                ProgressView()
                    .controlSize(.small)
                InstrumentLabel(text: "ASKING THE PEER")
            } else {
                Text(model.audition.error)
                    .font(Theme.sans(12))
                    .foregroundStyle(Theme.statusError)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func content(state: AuditionState, position: Double) -> some View {

        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header(state: state)

                WaveformView(
                    peaks: model.player.peaks,
                    progress: model.player.duration > 0 ? position / model.player.duration : 0,
                    onSeek: { fraction in
                        model.player.seek(to: fraction * model.player.duration)
                    }
                )
                .frame(height: compact ? 90 : 132)
                .padding(.horizontal, 16)

                facts(state: state, position: position)
                    .padding(.horizontal, 16)

                if !model.audition.note.isEmpty {
                    Text(model.audition.note)
                        .font(Theme.sans(11))
                        .foregroundStyle(Theme.statusSaved)
                        .padding(.horizontal, 16)
                }

                if !model.player.errorText.isEmpty {
                    Text(model.player.errorText)
                        .font(Theme.sans(11))
                        .foregroundStyle(Theme.statusError)
                        .padding(.horizontal, 16)
                }

                catalogue(state: state)
                    .padding(.horizontal, 16)

                Spacer(minLength: 8)
            }
            .padding(.vertical, 18)
        }
    }

    private func header(state: AuditionState) -> some View {

        HStack(alignment: .top, spacing: 16) {
            artwork(state: state)

            VStack(alignment: .leading, spacing: 8) {
                Text(state.filename)
                    .font(Theme.sans(20, .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    InstrumentLabel(text: sourceBadge(state))
                    InstrumentLabel(text: state.username)

                    if state.kept {
                        StatusChip(text: model.audition.keptStatus.isEmpty ? "kept" : model.audition.keptStatus,
                                   color: Theme.statusSaved)
                    }
                }

                if let match = state.catalogue.first {
                    Text("\(match.artist) — \(match.title)")
                        .font(Theme.sans(13))
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                }

                HStack(spacing: 8) {
                    Button {
                        model.player.toggle()
                    } label: {
                        Label(model.player.isPlaying ? "Pause" : "Play",
                              systemImage: model.player.isPlaying ? "pause.fill" : "play.fill")
                    }
                    .buttonStyle(DigPrimaryKeyStyle())
                    .frame(width: 96)

                    Button("Keep") {
                        Task { await model.keep() }
                    }
                    .buttonStyle(DigKeyStyle())
                    .disabled(state.kept || model.audition.isKept)

                    if let url = model.player.localFileURL {
                        Label("Drag to Ableton", systemImage: "square.and.arrow.up")
                            .font(Theme.sans(11, .medium))
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.horizontal, 10)
                            .frame(height: Theme.keyHeight)
                            .background(RoundedRectangle(cornerRadius: Theme.radiusKey).fill(Theme.bgControl))
                            .overlay(alignment: .center) {
                                DragOutHandle(fileURL: url)
                            }
                            .overlay(RoundedRectangle(cornerRadius: Theme.radiusKey)
                                .strokeBorder(Theme.border, lineWidth: 1))
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
    }

    private func artwork(state: AuditionState) -> some View {

        ZStack {
            RoundedRectangle(cornerRadius: Theme.radiusPanel).fill(Theme.bgElevated)

            if let url = state.catalogue.first?.artworkURL {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Image(systemName: "waveform")
                        .font(.system(size: 22, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                .clipShape(RoundedRectangle(cornerRadius: Theme.radiusPanel))
            } else {
                Image(systemName: "waveform")
                    .font(.system(size: 22, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .frame(width: compact ? 80 : 96, height: compact ? 80 : 96)
        .overlay(RoundedRectangle(cornerRadius: Theme.radiusPanel)
            .strokeBorder(Theme.border, lineWidth: 1))
    }

    private func facts(state: AuditionState, position: Double) -> some View {

        HStack(spacing: 0) {
            fact("POSITION", TimeFormat.clock(position))
            fact("DURATION", TimeFormat.clock(model.player.duration))
            fact("SOURCE", sourceBadge(state))
            fact("PEER", peerFact(state))

            if let match = state.catalogue.first {
                fact("MATCH", String(format: "%.2f", match.score))
            }
        }
        .padding(.vertical, 12)
        .padding(.horizontal, 14)
        .background(RoundedRectangle(cornerRadius: Theme.radiusPanel).fill(Theme.bgCard))
        .overlay(RoundedRectangle(cornerRadius: Theme.radiusPanel)
            .strokeBorder(Theme.border, lineWidth: 1))
    }

    private func fact(_ label: String, _ value: String) -> some View {

        VStack(alignment: .leading, spacing: 4) {
            InstrumentLabel(text: label, color: Theme.textMuted)
            Text(value)
                .font(Theme.mono(11))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func catalogue(state: AuditionState) -> some View {

        VStack(alignment: .leading, spacing: 8) {
            InstrumentLabel(text: state.catalogueState == "pending" ? "CATALOGUE · LOOKING…" : "CATALOGUE")

            if state.catalogue.isEmpty {
                Text(state.catalogueState == "pending"
                     ? "Querying iTunes, then YouTube for the long version."
                     : "No catalogue match. The peer's file is the only source.")
                    .font(Theme.sans(11))
                    .foregroundStyle(Theme.textMuted)
            } else {
                ForEach(state.catalogue.prefix(3)) { match in
                    HStack(spacing: 10) {
                        Text(match.label)
                            .font(Theme.sans(12))
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)

                        Spacer()

                        InstrumentLabel(text: match.source)
                        Text(String(format: "%.2f", match.score))
                            .font(Theme.mono(10))
                            .foregroundStyle(Theme.textTertiary)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 30)
                    .background(RoundedRectangle(cornerRadius: Theme.radiusPad).fill(Theme.bgCard))
                    .overlay(RoundedRectangle(cornerRadius: Theme.radiusPad)
                        .strokeBorder(Theme.border, lineWidth: 1))
                }
            }
        }
    }

    private func sourceBadge(_ state: AuditionState) -> String {

        guard let source = state.source else { return "RESOLVING" }

        switch source.kind {
        case .local: return "LOCAL"
        case .peer: return source.complete ? "PEER · FILE" : "PEER · PARTIAL"
        case .catalogue: return "CATALOGUE"
        }
    }

    private func peerFact(_ state: AuditionState) -> String {

        let peer = state.peer

        if peer.bytes == 0 {
            return peer.status
        }

        return "\(Int(peer.percent))% · \(peer.status)"
    }
}

// MARK: - Middle column for the Audition section

struct AuditionColumn: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let state = model.audition.state {
                HStack {
                    InstrumentLabel(text: "AUDITION")
                    Spacer()
                    Button("Close") {
                        Task { await model.closeAudition() }
                    }
                    .buttonStyle(DigKeyStyle(dense: true))
                }
                .padding(.horizontal, 12)
                .frame(height: 44)

                Divider().overlay(Theme.border)

                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        pair("User", state.username)
                        pair("File", state.filename)
                        pair("Folder", state.folder)
                        pair("Peer", state.peer.status)
                        if state.source?.kind != .local, state.peer.size > 0 {
                            pair("Bytes", ByteCountFormatter.string(
                                fromByteCount: state.peer.bytes, countStyle: .binary)
                                 + " / " + ByteCountFormatter.string(
                                    fromByteCount: state.peer.size, countStyle: .binary))
                        }
                        pair("Catalogue", state.catalogueState)

                        if !state.peer.partialPath.isEmpty {
                            pair("Partial", (state.peer.partialPath as NSString).lastPathComponent)
                        }

                        if !state.peer.error.isEmpty {
                            Text(state.peer.error)
                                .font(Theme.sans(11))
                                .foregroundStyle(Theme.statusError)
                        }
                    }
                    .padding(12)
                }

            } else {
                PlaceholderColumn(title: "Audition",
                                  body: "Rule: Enter on a file. This column shows the peer fetch and catalogue state while it resolves.")
            }
        }
        .background(Theme.bgCanvas)
    }

    private func pair(_ label: String, _ value: String) -> some View {

        VStack(alignment: .leading, spacing: 3) {
            InstrumentLabel(text: label, color: Theme.textMuted)
            Text(value)
                .font(Theme.sans(11))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
