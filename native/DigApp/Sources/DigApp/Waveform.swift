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

        let barWidth: CGFloat = 1
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

        for index in 0..<count {
            let fraction = Double(index) / Double(count)
            let peakIndex = min(peaks.count - 1, Int(fraction * Double(peaks.count)))
            let amplitude = CGFloat(peaks[peakIndex])
            let barHeight = max(1, amplitude * (size.height - 4))
            let x = CGFloat(index) * stride
            let rect = CGRect(x: x, y: middle - barHeight / 2, width: barWidth, height: barHeight)
            let color = x <= playedX ? Theme.waveAmber : Theme.waveGraphite

            context.fill(Path(rect), with: .color(color))
        }
    }
}
