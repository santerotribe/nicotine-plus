// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Hardware materials, borrowed from the panels in the synthRef "UI Mother"
/// archive: matte caps with a top light and a bottom shade, milled wells, LEDs,
/// knurled grips and one lit accent. Intensity is kept low: this is a Mac app,
/// not a plugin faceplate.
enum Material {

    // Caps: the surface a control sits on top of.
    static var capTop: Color { Palette.shade(0x2B2E31, 0x26262A) }
    static var capBottom: Color { Palette.shade(0x1B1D1F, 0x17171A) }
    static var capPressedTop: Color { Palette.shade(0x16181A, 0x121214) }
    static var capPressedBottom: Color { Palette.shade(0x1D1F21, 0x1B1B1E) }

    // Chrome: the anodised panels the controls sit on.
    static var chrome: LinearGradient {
        LinearGradient(
            colors: Palette.active == .suno
                ? [Color(hex: 0x17171A), Color(hex: 0x111113)]
                : [Color(hex: 0x1F2224), Color(hex: 0x191B1D)],
            startPoint: .top, endPoint: .bottom
        )
    }

    // Wells: the surface things sit inside (search field, waveform housing, displays).
    static var well: Color { Palette.shade(0x15171A, 0x0D0D0F) }
    static var wellEdge: Color { Palette.shade(0x0E1011, 0x08080A) }

    // Lights.
    static let rimTop = Color.white.opacity(0.07)
    static let rimBottom = Color.black.opacity(0.65)
    static let innerShade = Color.black.opacity(0.45)
    static let innerLight = Color.white.opacity(0.05)

    // The lit accent, warmer in its core than the flat gold.
    static var litCore: Color { Palette.shade(0xFFDF9A, 0xEFD6A2) }
    static var litMid: Color { Palette.shade(0xFFC64B, 0xD4A54A) }
    static var litEdge: Color { Palette.shade(0xE2A62F, 0xA87C2E) }
    static var litInk: Color { Palette.shade(0x241A05, 0x1A1408) }
}

/// A raised cap: vertical gradient, dark outer edge, light along the top.
struct CapSurface: View {

    var radius: CGFloat
    var pressed = false
    var lit = false

    var body: some View {

        let top = lit ? Material.litCore : (pressed ? Material.capPressedTop : Material.capTop)
        let bottom = lit ? Material.litEdge : (pressed ? Material.capPressedBottom : Material.capBottom)

        RoundedRectangle(cornerRadius: radius)
            .fill(LinearGradient(colors: [top, bottom], startPoint: .top, endPoint: .bottom))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.black.opacity(0.55), lineWidth: 1)
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(
                        LinearGradient(
                            colors: [Material.rimTop, .clear, Color.black.opacity(0.35)],
                            startPoint: .top, endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            )
            .overlay {
                if pressed {
                    // The cap has travelled: a shadow gathers along the top edge.
                    RoundedRectangle(cornerRadius: radius)
                        .fill(
                            LinearGradient(
                                colors: [Material.innerShade, .clear],
                                startPoint: .top, endPoint: .center
                            )
                        )
                        .allowsHitTesting(false)
                }
            }
    }
}

/// A milled well: things inside it catch shadow along the top and light at the
/// bottom, which is the whole difference between a field and a cap.
struct WellSurface: View {

    var radius: CGFloat
    var tint: Color = .clear

    var body: some View {
        RoundedRectangle(cornerRadius: radius)
            .fill(Material.well)
            .overlay {
                if tint != .clear {
                    RoundedRectangle(cornerRadius: radius).fill(tint)
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Material.wellEdge, lineWidth: 1)
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(
                        LinearGradient(
                            colors: [Color.black.opacity(0.55), .clear, Material.innerLight],
                            startPoint: .top, endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            )
    }
}

/// Vertical knurling, for grips: 1 px lines, 3 px apart, barely there.
struct Knurling: View {

    var spacing: CGFloat = 3
    var opacity: Double = 0.07

    var body: some View {
        Canvas { context, size in
            var x: CGFloat = 1

            while x < size.width {
                context.fill(
                    Path(CGRect(x: x, y: 3, width: 1, height: size.height - 6)),
                    with: .color(.white.opacity(opacity))
                )
                x += spacing
            }
        }
        .allowsHitTesting(false)
    }
}

/// A status LED: off is a dark dot, on carries both colour and a little bloom.
struct LED: View {

    var isOn = true
    var color: Color = Theme.accent
    var size: CGFloat = 5

    var body: some View {
        Circle()
            .fill(isOn ? color : Color(hex: 0x35393B))
            .frame(width: size, height: size)
            .overlay(Circle().strokeBorder(Color.black.opacity(0.7), lineWidth: 0.5))
            .overlay {
                if isOn {
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [.white.opacity(0.85), color.opacity(0.0)],
                                center: .init(x: 0.35, y: 0.3),
                                startRadius: 0,
                                endRadius: size * 1.2
                            )
                        )
                        .frame(width: size * 0.7, height: size * 0.7)
                        .offset(x: -size * 0.12, y: -size * 0.15)
                        .blendMode(.plusLighter)
                }
            }
            .shadow(color: isOn ? color.opacity(0.55) : .clear, radius: 4)
            .animation(.easeOut(duration: 0.12), value: isOn)
    }
}

/// The thin bright edge a panel catches along its top.
struct PanelRim: View {

    var body: some View {
        LinearGradient(
            colors: [.white.opacity(0.06), .clear],
            startPoint: .top, endPoint: .bottom
        )
        .frame(height: 1)
        .allowsHitTesting(false)
    }
}
