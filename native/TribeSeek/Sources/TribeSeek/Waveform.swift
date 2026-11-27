// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

enum TimeFormat {

    static func clock(_ seconds: Double) -> String {

        guard seconds.isFinite, seconds >= 0 else { return "0:00" }

        let total = Int(seconds.rounded())
        let minutes = total / 60
        let remainder = total % 60

        return String(format: "%d:%02d", minutes, remainder)
    }
}

/// 1 pt bars, amber for the played part, graphite for the rest.
struct WaveformView: View {

    let peaks: [Float]
    let progress: Double
    var interactive = true
    var onSeek: ((Double) -> Void)?

    @State private var isScrubbing = false

    var body: some View {
        GeometryReader { geometry in
            Canvas { context, size in
                draw(context: &context, size: size)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        guard interactive, geometry.size.width > 0 else { return }
                        isScrubbing = true
                        onSeek?(clamp(value.location.x / geometry.size.width))
                    }
                    .onEnded { value in
                        guard interactive, geometry.size.width > 0 else { return }
                        isScrubbing = false
                        onSeek?(clamp(value.location.x / geometry.size.width))
                    }
            )
        }
    }

    private func clamp(_ value: Double) -> Double {
        max(0, min(1, value))
    }

    private func draw(context: inout GraphicsContext, size: CGSize) {

        // 2 px bars read as a meter; 1 px reads as a barcode.
        let barWidth: CGFloat = 2
        let gap: CGFloat = 2
        let stride = barWidth + gap
        let count = max(1, Int(size.width / stride))
        let middle = size.height / 2
        let playedX = size.width * clamp(progress)

        guard !peaks.isEmpty else {
            context.fill(
                Path(CGRect(x: 0, y: middle - 0.5, width: size.width, height: 1)),
                with: .color(Theme.waveGraphite)
            )
            return
        }

        // A hairline through the middle: the reference panels draw their meters
        // around a zero line, and it keeps sparse waveforms from floating.
        context.fill(
            Path(CGRect(x: 0, y: middle - 0.5, width: size.width, height: 1)),
            with: .color(Color.white.opacity(0.05))
        )

        for index in 0..<count {
            let start = Double(index) / Double(count)
            let end = Double(index + 1) / Double(count)
            let from = min(peaks.count - 1, Int(start * Double(peaks.count)))
            let to = min(peaks.count - 1, max(from, Int(end * Double(peaks.count))))
            let slice = (from...to).map { peaks[$0] }
            let peak = CGFloat(slice.max() ?? 0)
            let body = CGFloat(slice.reduce(0, +) / Float(slice.count))
            let x = CGFloat(index) * stride
            let isPlayed = x <= playedX
            let height = max(1, body * (size.height - 6))

            // A meter, not a silhouette: an RMS body with a peak tick above it.
            let rect = CGRect(x: x, y: middle - height / 2, width: barWidth, height: height)
            let color = isPlayed ? Material.litMid : Theme.waveGraphite

            context.fill(Path(rect), with: .color(color))

            if peak > body + 0.06 {
                let peakHeight = max(1, peak * (size.height - 6))
                let tick = CGRect(
                    x: x, y: middle - peakHeight / 2, width: barWidth, height: 1.5
                )
                context.fill(
                    Path(tick),
                    with: .color(isPlayed ? Material.litCore : Theme.waveGraphitePeak)
                )
            }

            // The bars just behind the playhead stay lit for a beat of air.
            if isPlayed && x > playedX - 18 {
                context.fill(Path(rect), with: .color(Material.litCore.opacity(0.45)))
            }
        }

        // Playhead: a 1 px lit line with a faint bloom, like the LEDs on the boards.
        if progress > 0 && progress < 1 {
            let line = CGRect(x: playedX, y: 2, width: 1, height: size.height - 4)
            context.fill(Path(line), with: .color(Material.litCore))
            context.fill(
                Path(CGRect(x: playedX - 2, y: 2, width: 5, height: size.height - 4)),
                with: .color(Material.litMid.opacity(0.12))
            )
        }
    }
}
