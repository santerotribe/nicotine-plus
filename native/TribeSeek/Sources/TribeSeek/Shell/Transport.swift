// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// The persistent instrument strip: always there, always the same register.
struct Transport: View {

    @Bindable var model: AppModel

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1.0 / 30.0)) { timeline in
            let position = model.player.position()
            let duration = model.player.duration

            HStack(spacing: 14) {
                playKey

                VStack(alignment: .leading, spacing: 2) {
                    Text(model.player.title.isEmpty ? "Nothing auditioning" : model.player.title)
                        .font(Theme.sans(12, .medium))
                        .foregroundStyle(model.player.title.isEmpty ? Theme.textMuted : Theme.textPrimary)
                        .lineLimit(1)

                    HStack(spacing: 8) {
                        InstrumentLabel(text: model.player.badge.isEmpty ? "IDLE" : model.player.badge,
                                        color: model.player.badge.isEmpty ? Theme.textMuted : Theme.textTertiary)

                        if let state = model.audition.state,
                           state.peer.queuePosition > 0,
                           state.source?.kind != .local {
                            Text("#" + String(state.peer.queuePosition))
                                .font(Theme.monoStrong(10))
                                .foregroundStyle(state.peer.percent > 0 ? Theme.accent : Theme.textTertiary)
                        }

                        if !model.player.errorText.isEmpty {
                            Text(model.player.errorText)
                                .font(Theme.sans(10))
                                .foregroundStyle(Theme.statusError)
                                .lineLimit(1)
                        }
                    }
                }
                .frame(width: 250, alignment: .leading)

                WaveformView(
                    peaks: compactPeaks,
                    progress: duration > 0 ? position / duration : 0,
                    interactive: true,
                    onSeek: { fraction in model.player.seek(to: fraction * duration) }
                )
                .frame(height: 22)
                .padding(.horizontal, 6)
                .background(WellSurface(radius: Theme.radiusPad))

                Text(TimeFormat.clock(position) + " / " + TimeFormat.clock(duration))
                    .font(Theme.monoStrong(11))
                    .foregroundStyle(Theme.textTertiary)
                    .monospacedDigit()
                    .padding(.horizontal, 8)
                    .frame(height: 22)
                    .background(WellSurface(radius: Theme.radiusPad))

                Spacer(minLength: 4)

                if model.audition.sessionID != nil {
                    keepKey

                    Rectangle()
                        .fill(Color.black.opacity(0.45))
                        .frame(width: 1, height: 20)
                        .overlay(Rectangle().fill(Color.white.opacity(0.04)).offset(x: 1))

                    dragHandle
                    closeKey
                }
            }
            .padding(.horizontal, 12)
            .frame(height: Theme.transportHeight)
            .background(Material.chrome)
            .overlay(alignment: .top) { PanelRim() }
            .id(timeline.date.timeIntervalSince1970)
        }
    }

    /// Downsample the whole track into the strip; never just its first slice.
    private var compactPeaks: [Float] {

        let peaks = model.player.peaks
        let target = 240

        guard peaks.count > target else { return peaks }

        let step = Double(peaks.count) / Double(target)

        return (0..<target).map { index in
            peaks[min(peaks.count - 1, Int(Double(index) * step))]
        }
    }

    private var playKey: some View {

        Button {
            if model.player.isReady {
                model.player.toggle()
            } else if let state = model.audition.state {
                model.apply(state)
            }
        } label: {
            Image(systemName: model.player.isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: 11, weight: .bold))
                .offset(x: model.player.isPlaying ? 0 : 0.5)
        }
        .buttonStyle(DigIconKeyStyle(diameter: 32, isOn: model.player.isPlaying,
                                     activeInk: Theme.accent))
        .amberFocus(16)
        .help(model.player.isPlaying ? "Pause" : "Play")
    }

    private var keepKey: some View {

        Button {
            Task { await model.keep() }
        } label: {
            Label(model.audition.isKept ? "Kept" : "Keep", systemImage: model.audition.isKept ? "checkmark" : "tray.and.arrow.down")
                .labelStyle(.titleAndIcon)
        }
        .buttonStyle(DigPrimaryKeyStyle())
        .disabled(model.audition.isKept)
        .opacity(model.audition.isKept ? 0.55 : 1)
        .amberFocus()
        .help(model.audition.isKept ? "Already in the crate" : "Add to the crate and separate")
    }

    private var dragHandle: some View {

        ZStack {
            if let url = model.player.localFileURL {
                DragOutHandle(fileURL: url)
            }

            HStack(spacing: 7) {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 11, weight: .medium))
                InstrumentLabel(text: "Drag", color: Theme.textSecondary)
            }
            .allowsHitTesting(false)
            .frame(width: 84, height: Theme.instrumentKeyHeight)
            .background(CapSurface(radius: Theme.radiusPad))
            .overlay(Knurling(spacing: 3, opacity: 0.05).clipShape(
                RoundedRectangle(cornerRadius: Theme.radiusPad)))
        }
        .frame(width: 84, height: Theme.instrumentKeyHeight)
        .help(model.player.localFileURL == nil
              ? "The audio is not on disk yet"
              : "Drag into Ableton or Finder")
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
}
