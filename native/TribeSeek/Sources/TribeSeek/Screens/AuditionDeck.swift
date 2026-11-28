// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import SwiftUI

/// The audition deck. One surface with two states: the compact strip when the
/// tray is closed, the ribbon when it is open. Replaces the old 300 pt scrolling
/// pane stacked on top of a 48 pt transport.
struct AuditionDeck: View {

    @Bindable var model: AppModel

    static let expandedHeight: CGFloat = 144

    var body: some View {
        if model.trayExpanded, model.audition.state != nil {
            RibbonDeck(model: model)
                .frame(height: Self.expandedHeight)
        } else {
            Transport(model: model)
        }
    }
}

// MARK: - Ribbon

private struct RibbonDeck: View {

    @Bindable var model: AppModel
    @State private var showStems = false

    var body: some View {
        GeometryReader { geometry in
            let wide = geometry.size.width > 1_180

            TimelineView(.periodic(from: .now, by: 1.0 / 30.0)) { _ in
                if let state = model.audition.state {
                    VStack(spacing: 0) {
                        header(state, wide: wide)
                        waveform
                        ribbon(state, wide: wide)
                    }
                    .background(Material.chrome)
                    .overlay(alignment: .top) { PanelRim() }
                }
            }
        }
    }

    // MARK: Header

    private func header(_ state: AuditionState, wide: Bool) -> some View {

        HStack(spacing: 9) {
            artwork(state)

            VStack(alignment: .leading, spacing: 1) {
                Text(state.filename)
                    .font(Theme.sans(12.5, .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Text(artistLine(state))
                    .font(Theme.sans(10))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            .frame(maxWidth: 330, alignment: .leading)

            StatusChip(text: badge(state), color: sourceColor(state))

            if wide {
                DeckChip(text: state.username)
            }

            if let rate = bitrateLabel(state) {
                DeckChip(text: rate)
            }

            DeckChip(text: sizeLabel(state))

            Spacer(minLength: 6)

            playKey
            keepKey(state)
            dragKey
            collapseKey
            closeKey
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Theme.border).frame(height: 1)
        }
    }

    private func artwork(_ state: AuditionState) -> some View {

        ZStack {
            RoundedRectangle(cornerRadius: 3).fill(Theme.bgElevated)

            if let url = state.catalogue.first?.artworkURL {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Image(systemName: "waveform")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                .clipShape(RoundedRectangle(cornerRadius: 3))
            } else {
                Image(systemName: "waveform")
                    .font(.system(size: 12, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .frame(width: 34, height: 34)
        .overlay(RoundedRectangle(cornerRadius: 3)
            .strokeBorder(Color.black.opacity(0.6), lineWidth: 1))
    }

    private var playKey: some View {

        Button {
            model.player.toggle()
        } label: {
            Image(systemName: model.player.isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: 10, weight: .bold))
        }
        .buttonStyle(DigIconKeyStyle(diameter: 30, isOn: model.player.isPlaying,
                                     activeInk: Theme.accent))
        .amberFocus(15)
        .help(model.player.isPlaying ? "Pause" : "Play")
    }

    private func keepKey(_ state: AuditionState) -> some View {

        let kept = state.kept || model.audition.isKept

        return HStack(spacing: 6) {
            Button(kept ? "Kept" : "Keep") {
                Task { await model.keep(kind: "sample") }
            }
            .buttonStyle(DigPrimaryKeyStyle())
            .disabled(kept)
            .opacity(kept ? 0.55 : 1)
            .amberFocus()
            .help("Keep to the Sample crate")

            Button("DJ") {
                Task { await model.keep(kind: "dj") }
            }
            .buttonStyle(DigKeyStyle(dense: true))
            .disabled(kept)
            .opacity(kept ? 0.55 : 1)
            .amberFocus()
            .help("Keep to the DJ crate")
        }
    }

    private var dragKey: some View {

        ZStack {
            if let url = draggableURL {
                DragOutHandle(fileURL: url)
            }

            Image(systemName: "square.and.arrow.up")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .allowsHitTesting(false)
        }
        .frame(width: 30, height: 30)
        .background(CapSurface(radius: Theme.radiusPad))
        .help(draggableURL == nil
              ? "The audio is not on disk yet"
              : "Drag into Ableton or Finder")
    }

    private var draggableURL: URL? {
        guard let url = model.player.localFileURL,
              !url.lastPathComponent.hasPrefix("INCOMPLETE") else { return nil }

        return url
    }

    private var collapseKey: some View {

        Button {
            model.trayExpanded = false
        } label: {
            Image(systemName: "chevron.down")
                .font(.system(size: 10, weight: .semibold))
        }
        .buttonStyle(DigIconKeyStyle(diameter: 26))
        .amberFocus(13)
        .help("Collapse the deck")
    }

    private var closeKey: some View {

        Button {
            Task { await model.closeAudition() }
        } label: {
            Image(systemName: "xmark")
                .font(.system(size: 10, weight: .semibold))
        }
        .buttonStyle(DigIconKeyStyle(diameter: 26))
        .amberFocus(13)
        .help("Close the audition")
    }

    // MARK: Waveform

    private var waveform: some View {

        let duration = model.player.duration
        let progress = duration > 0 ? model.player.position() / duration : 0

        return WaveformView(peaks: compactPeaks, progress: progress, interactive: true) { fraction in
            guard duration > 0 else { return }
            model.player.seek(to: fraction * duration)
        }
        .frame(height: 36)
        .padding(.horizontal, 6)
        .background(WellSurface(radius: Theme.radiusPad))
        .padding(.horizontal, 12)
        .padding(.top, 8)
    }

    private var compactPeaks: [Float] {

        let peaks = model.player.peaks
        let target = 300

        guard peaks.count > target else { return peaks }

        let step = Double(peaks.count) / Double(target)

        return (0..<target).map { index in
            peaks[min(peaks.count - 1, Int(Double(index) * step))]
        }
    }

    // MARK: Ribbon

    private func ribbon(_ state: AuditionState, wide: Bool) -> some View {

        HStack(spacing: 0) {
            cell("POSITION", width: 112) {
                Text("\(TimeFormat.clock(model.player.position())) / \(TimeFormat.clock(model.player.duration))")
            }

            rule

            cell(badge(state), width: 310) {
                peerValue(state)
            }

            rule

            cell("MATCH", width: 138) {
                matchValue(state)
            }

            rule

            cell("STEMS", width: 188) {
                Button {
                    showStems.toggle()
                } label: {
                    stemsValue(state)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .popover(isPresented: $showStems, arrowEdge: .bottom) {
                    StemsPopover(model: model)
                }
            }

            rule

            cell("CATALOGUE", width: nil) {
                catalogueValue(state, wide: wide)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(height: 38)
        .background(
            RoundedRectangle(cornerRadius: 4).fill(Color.black.opacity(0.22))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4).strokeBorder(Theme.border, lineWidth: 1)
        )
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 10)
    }

    private var rule: some View {

        Rectangle()
            .fill(Theme.border)
            .frame(width: 1)
            .padding(.vertical, 6)
    }

    private func cell<Content: View>(_ label: String, width: CGFloat?,
                                     @ViewBuilder content: () -> Content) -> some View {

        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(Theme.mono(8))
                .tracking(1.05)
                .foregroundStyle(Theme.textMuted)
                .lineLimit(1)

            content()
                .font(Theme.mono(10.5))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 10)
        .frame(width: width, alignment: .leading)
    }

    @ViewBuilder
    private func peerValue(_ state: AuditionState) -> some View {

        if state.source?.kind == .local {
            Text("local file").foregroundStyle(Theme.textMuted)

        } else if state.peer.bytes == 0 {
            Text(state.peer.status).foregroundStyle(Theme.textMuted)

        } else {
            HStack(spacing: 7) {
                Text("\(Int(state.peer.percent))%")

                Capsule()
                    .fill(Color.black.opacity(0.5))
                    .frame(width: 64, height: 3)
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(Theme.accent.opacity(0.85))
                            .frame(width: 64 * max(0.02, min(1, state.peer.percent / 100)))
                    }

                Text("\(megabytes(state.peer.bytes)) / \(megabytes(state.peer.size)) MB")
                    .foregroundStyle(Theme.textMuted)
            }
        }
    }

    @ViewBuilder
    private func matchValue(_ state: AuditionState) -> some View {

        if let score = state.catalogue.first?.score {
            HStack(spacing: 6) {
                Text(String(format: "%.2f", score))
                    .foregroundStyle(Theme.accent)

                HStack(spacing: 2) {
                    ForEach(0..<5, id: \.self) { index in
                        Circle()
                            .fill(Double(index) < score * 5
                                  ? Theme.accent
                                  : Color.black.opacity(0.45))
                            .frame(width: 4, height: 4)
                    }
                }
            }

        } else {
            Text("—").foregroundStyle(Theme.textMuted)
        }
    }

    @ViewBuilder
    private func stemsValue(_ state: AuditionState) -> some View {

        if model.audition.isSeparating {
            HStack(spacing: 5) {
                LED(color: Theme.accent, size: 4)
                Text("separating…").foregroundStyle(Theme.accent)
            }

        } else if !model.audition.stems.isEmpty {
            Text("\(model.audition.stems.count) stems")
                .foregroundStyle(Theme.statusSaved)

        } else {
            Text("— keep to separate").foregroundStyle(Theme.textMuted)
        }
    }

    @ViewBuilder
    private func catalogueValue(_ state: AuditionState, wide: Bool) -> some View {

        if state.catalogue.isEmpty {
            Text(state.catalogueState == "pending" ? "looking…" : "no match")
                .foregroundStyle(Theme.textMuted)

        } else if wide {
            HStack(spacing: 4) {
                ForEach(state.catalogue.prefix(3)) { match in
                    DeckChip(text: "\(short(match.label)) \(String(format: "%.2f", match.score))")
                }
            }

        } else {
            DeckChip(text: "\(state.catalogue.count) matches ›")
        }
    }

    // MARK: Copy

    private func badge(_ state: AuditionState) -> String {

        guard let source = state.source else { return "RESOLVING" }

        switch source.kind {
        case .local: return "LOCAL"
        case .peer: return source.complete ? "PEER · FILE" : "PEER · PARTIAL"
        case .catalogue: return "CATALOGUE"
        }
    }

    private func sourceColor(_ state: AuditionState) -> Color {

        switch state.source?.kind {
        case .local: return Theme.accent
        case .peer: return Theme.statusSaved
        case .catalogue: return Theme.textSecondary
        case nil: return Theme.textMuted
        }
    }

    private func artistLine(_ state: AuditionState) -> String {

        if let match = state.catalogue.first, match.score >= 0.55 {
            return "\(match.artist) — \(match.title)"
        }

        return state.folder.isEmpty ? state.username : state.folder
    }

    private func bitrateLabel(_ state: AuditionState) -> String? {

        if state.filename.lowercased().hasSuffix(".flac") {
            return "FLAC"
        }

        guard state.duration > 0, state.size > 0 else { return nil }

        let value = Int((Double(state.size) * 8 / state.duration / 1_000).rounded())

        guard value > 0 else { return nil }

        return "\(value) KBPS"
    }

    private func sizeLabel(_ state: AuditionState) -> String {
        ByteCountFormatter.string(fromByteCount: state.size, countStyle: .binary)
    }

    private func megabytes(_ bytes: Int64) -> String {
        String(format: "%.1f", Double(bytes) / 1_048_576)
    }

    private func short(_ value: String, limit: Int = 20) -> String {
        value.count <= limit ? value : String(value.prefix(limit - 1)) + "…"
    }
}

// MARK: - Chip

private struct DeckChip: View {

    let text: String
    var hot = false

    var body: some View {
        Text(text.uppercased())
            .font(Theme.mono(8))
            .tracking(0.9)
            .foregroundStyle(hot ? Theme.accent : Theme.textTertiary)
            .lineLimit(1)
            .padding(.horizontal, 5)
            .frame(height: 16)
            .background(
                RoundedRectangle(cornerRadius: 3)
                    .fill(hot ? Theme.accent.opacity(0.06) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 3)
                    .strokeBorder(hot ? Theme.accent.opacity(0.5) : Theme.borderMedium,
                                  lineWidth: 1)
            )
    }
}


// MARK: - Stems

private struct StemsPopover: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                InstrumentLabel(text: "STEMS")

                Spacer()

                Text("\(model.audition.stems.count)")
                    .font(Theme.mono(9))
                    .foregroundStyle(Theme.textTertiary)
            }

            if model.audition.stems.isEmpty {
                Text("Keep the track to separate it into stems.")
                    .font(Theme.sans(11))
                    .foregroundStyle(Theme.textMuted)
            } else {
                ForEach(model.audition.stems) { stem in
                    HStack(spacing: 8) {
                        LED(isOn: stem.exists,
                            color: stem.exists ? Theme.statusSaved : Theme.statusError,
                            size: 4)

                        Text(stem.name.uppercased())
                            .font(Theme.mono(10))
                            .tracking(0.8)
                            .foregroundStyle(Theme.textSecondary)

                        Spacer()

                        ZStack {
                            if stem.exists {
                                DragOutHandle(fileURL: stem.url)
                            }

                            HStack(spacing: 5) {
                                Image(systemName: "square.and.arrow.up")
                                    .font(.system(size: 9, weight: .medium))
                                InstrumentLabel(text: "DRAG", color: Theme.textSecondary, tracking: 0.8)
                            }
                            .allowsHitTesting(false)
                        }
                        .frame(width: 68, height: 24)
                        .background(CapSurface(radius: Theme.radiusPad))
                    }
                    .frame(height: 28)
                }
            }
        }
        .padding(12)
        .frame(width: 320)
        .background(Theme.bgWorkspace)
    }
}

