// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

// MARK: - Keys

/// The library key: a matte cap that catches light along its top edge, sinks
/// when pressed, and lights an LED when it is holding a state.
struct DigKeyStyle: ButtonStyle {

    var dense = false
    var danger = false
    var isOn = false

    func makeBody(configuration: Configuration) -> some View {
        Face(configuration: configuration, style: self)
    }

    private struct Face: View {

        let configuration: ButtonStyleConfiguration
        let style: DigKeyStyle

        @Environment(\.isEnabled) private var enabled
        @State private var hover = false

        var body: some View {
            let pressed = configuration.isPressed && enabled
            let ink: Color = !enabled ? Theme.textMuted
                : style.danger ? Theme.statusError
                : (hover || pressed || style.isOn) ? Theme.textPrimary : Theme.textSecondary

            configuration.label
                .font(Theme.sans(style.dense ? 11 : 12, .medium))
                .foregroundStyle(ink)
                .shadow(color: .black.opacity(pressed ? 0 : 0.45), radius: 0, y: 0.5)
                .padding(.horizontal, style.dense ? 10 : 12)
                .frame(height: style.dense ? 24 : (style.isOn ? 30 : Theme.keyHeight))
                .background(
                    CapSurface(radius: Theme.radiusKey, pressed: pressed,
                               lit: style.isOn || (hover && !pressed))
                )
                .overlay(alignment: .topLeading) {
                    if style.isOn {
                        LED(color: Theme.accent, size: 4)
                            .padding(.leading, 6)
                            .padding(.top, 6)
                    }
                }
                .contentShape(Rectangle())
                .onHover { hover = $0 && enabled }
                .animation(.easeInOut(duration: 0.12), value: hover)
                .animation(.easeOut(duration: 0.09), value: pressed)
        }
    }
}

/// The instrument key: smaller radius, mono upper case, and an optional LED,
/// so the transport reads like the panel it is modelled on.
struct DigInstrumentKeyStyle: ButtonStyle {

    var isOn = false
    var danger = false
    var ledColor: Color = Theme.accent

    func makeBody(configuration: Configuration) -> some View {
        Face(configuration: configuration, style: self)
    }

    private struct Face: View {

        let configuration: ButtonStyleConfiguration
        let style: DigInstrumentKeyStyle

        @Environment(\.isEnabled) private var enabled
        @State private var hover = false

        var body: some View {
            let pressed = configuration.isPressed && enabled
            let ink: Color = !enabled ? Theme.textMuted
                : style.danger ? Theme.statusError
                : (hover || pressed || style.isOn) ? Theme.textPrimary : Theme.textTertiary

            HStack(spacing: 6) {
                if style.isOn {
                    LED(color: style.ledColor, size: 4)
                }

                configuration.label
                    .font(Theme.mono(10))
                    .tracking(1.0)
                    .textCase(.uppercase)
            }
            .foregroundStyle(ink)
            .padding(.horizontal, 10)
            .frame(height: Theme.instrumentKeyHeight)
            .background(
                CapSurface(radius: Theme.radiusPad, pressed: pressed,
                           lit: hover && !pressed)
            )
            .contentShape(Rectangle())
            .onHover { hover = $0 && enabled }
            .animation(.easeInOut(duration: 0.12), value: hover)
        }
    }
}

/// The one lit action on a screen: a warm cap with a gloss band and a small
/// bloom, the way an illuminated key looks on the reference panels.
struct DigPrimaryKeyStyle: ButtonStyle {

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.sans(12, .semibold))
            .tracking(0.1)
            .foregroundStyle(Material.litInk)
            .padding(.horizontal, 16)
            .frame(height: 32)
            .background(
                RoundedRectangle(cornerRadius: Theme.radiusKey)
                    .fill(
                        LinearGradient(
                            colors: configuration.isPressed
                                ? [Material.litMid, Material.litEdge]
                                : [Material.litCore, Material.litMid, Material.litEdge],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    .overlay(alignment: .top) {
                        // Glass: a soft band of light across the upper third.
                        RoundedRectangle(cornerRadius: Theme.radiusKey)
                            .fill(
                                LinearGradient(
                                    colors: [.white.opacity(0.55), .white.opacity(0.0)],
                                    startPoint: .top, endPoint: .bottom
                                )
                            )
                            .frame(height: 13)
                            .padding(.horizontal, 1)
                            .padding(.top, 1)
                            .blendMode(.softLight)
                            .allowsHitTesting(false)
                    }
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.radiusKey)
                            .strokeBorder(Color.black.opacity(0.35), lineWidth: 1)
                    )
                    .shadow(color: Material.litMid.opacity(configuration.isPressed ? 0.18 : 0.38),
                            radius: configuration.isPressed ? 5 : 11, y: 1)
            )
            .contentShape(Rectangle())
    }
}

/// A machined round key for icon actions (top strip, transport).
struct DigIconKeyStyle: ButtonStyle {

    var diameter: CGFloat = 28
    var isOn = false
    var ledColor: Color = Theme.accent
    var activeInk: Color = Theme.textPrimary

    func makeBody(configuration: Configuration) -> some View {
        Face(configuration: configuration, style: self)
    }

    private struct Face: View {

        let configuration: ButtonStyleConfiguration
        let style: DigIconKeyStyle

        @Environment(\.isEnabled) private var enabled
        @State private var hover = false

        var body: some View {
            let pressed = configuration.isPressed && enabled
            let ink = !enabled ? Theme.textMuted
                : style.isOn ? style.activeInk
                : (hover || pressed) ? Theme.textPrimary : Theme.textTertiary

            configuration.label
                .font(.system(size: style.diameter * 0.38, weight: .medium))
                .foregroundStyle(ink)
                .frame(width: style.diameter, height: style.diameter)
                .background(
                    Circle().fill(
                        LinearGradient(
                            colors: pressed
                                ? [Material.capPressedBottom, Material.capPressedTop]
                                : [Material.capTop, Material.capBottom],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    .overlay(Circle().strokeBorder(Color.black.opacity(0.55), lineWidth: 1))
                    .overlay(
                        Circle().strokeBorder(
                            LinearGradient(
                                colors: [Material.rimTop, .clear, Color.black.opacity(0.3)],
                                startPoint: .top, endPoint: .bottom
                            ),
                            lineWidth: 1
                        )
                    )
                    .shadow(color: .black.opacity(0.35), radius: 1.5, y: 1)
                )
                .overlay(alignment: .bottomTrailing) {
                    if style.isOn {
                        LED(color: style.ledColor, size: 4)
                            .offset(x: 1, y: 1)
                    }
                }
                .contentShape(Circle())
                .onHover { hover = $0 && enabled }
                .animation(.easeInOut(duration: 0.12), value: hover)
        }
    }
}

// MARK: - Focus

/// Amber focus ring. The ring follows the control's own focus state, so it
/// appears with macOS keyboard navigation and never interferes with clicks.
struct AmberFocusRing: ViewModifier {

    var radius: CGFloat
    @FocusState private var focused: Bool

    func body(content: Content) -> some View {
        content
            .focused($focused)
            .focusEffectDisabled()
            .overlay {
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Theme.accent.opacity(focused ? 0.9 : 0), lineWidth: 2)
                    .padding(-3)
                    .allowsHitTesting(false)
            }
            .animation(.easeOut(duration: 0.1), value: focused)
    }
}

extension View {

    func amberFocus(_ radius: CGFloat = Theme.radiusKey) -> some View {
        modifier(AmberFocusRing(radius: radius))
    }
}

// MARK: - Labels and chips

/// Instrument register label: mono, upper case, tracked, with an engraved edge.
struct InstrumentLabel: View {

    let text: String
    var color: Color = Theme.textTertiary
    var tracking: CGFloat = 1.0

    var body: some View {
        Text(text.uppercased())
            .font(Theme.mono(10))
            .tracking(tracking)
            .foregroundStyle(color)
            .shadow(color: .black.opacity(0.6), radius: 0, y: 0.5)
    }
}

/// A status chip with an LED: the colour lives in the dot, not in a wash.
struct StatusChip: View {

    let text: String
    var color: Color = Theme.textTertiary

    var body: some View {
        HStack(spacing: 5) {
            LED(color: color, size: 4)

            Text(text.uppercased())
                .font(Theme.mono(9))
                .tracking(0.9)
                .foregroundStyle(color)
        }
        .padding(.horizontal, 7)
        .frame(height: 20)
        .background(
            RoundedRectangle(cornerRadius: Theme.radiusPad)
                .fill(Color.black.opacity(0.28))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.radiusPad)
                        .strokeBorder(Color.black.opacity(0.55), lineWidth: 1)
                )
        )
    }
}

// MARK: - Fields

/// A milled slot rather than a filled box: darker than the panel, shadow at the
/// top, a thin light along the bottom.
struct DigSearchField: View {

    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.textMuted)

            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
                .font(Theme.sans(12))
                .foregroundStyle(Theme.textPrimary)

            if !text.isEmpty {
                Button {
                    text = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textMuted)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .frame(height: 28)
        .background(WellSurface(radius: Theme.radiusKey))
    }
}

// MARK: - Avatars

/// A monogram in a bezel: the same top-light grammar as the caps.
struct Monogram: View {

    let text: String
    var size: CGFloat = 40
    var imageURL: URL?

    var body: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Material.capTop, Material.capBottom],
                        startPoint: .top, endPoint: .bottom
                    )
                )

            if let imageURL {
                AsyncImage(url: imageURL) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    initials
                }
                .clipShape(Circle())
            } else {
                initials
            }
        }
        .frame(width: size, height: size)
        .overlay(Circle().strokeBorder(Color.black.opacity(0.55), lineWidth: 1))
        .overlay(
            Circle().strokeBorder(
                LinearGradient(
                    colors: [Material.rimTop, .clear, Color.black.opacity(0.35)],
                    startPoint: .top, endPoint: .bottom
                ),
                lineWidth: 1
            )
        )
        .shadow(color: .black.opacity(0.35), radius: 1.5, y: 1)
    }

    private var initials: some View {
        Text(text.prefix(2).uppercased())
            .font(Theme.sans(size * 0.33, .semibold))
            .foregroundStyle(Theme.textSecondary)
            .shadow(color: .black.opacity(0.6), radius: 0, y: 0.5)
    }
}
