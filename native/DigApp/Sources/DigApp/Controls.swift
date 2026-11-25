// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Library register key: hairline box that fills on hover and sinks when pressed.
struct DigKeyStyle: ButtonStyle {

    var dense = false
    var danger = false

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
                : (hover || pressed) ? Theme.textPrimary : Theme.textSecondary
            let face: Color = !enabled ? .clear
                : pressed ? Theme.bgWaveCanvas
                : hover ? Theme.bgHover : .clear

            configuration.label
                .font(Theme.sans(style.dense ? 11 : 12, .medium))
                .foregroundStyle(ink)
                .padding(.horizontal, style.dense ? 10 : 12)
                .frame(height: style.dense ? 24 : Theme.keyHeight)
                .background(RoundedRectangle(cornerRadius: Theme.radiusKey).fill(face))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.radiusKey)
                        .strokeBorder(hover || pressed ? Theme.borderMedium : Theme.border, lineWidth: 1)
                )
                .overlay(alignment: .top) {
                    if pressed {
                        Rectangle().fill(Color.black.opacity(0.35)).frame(height: 1)
                            .clipShape(RoundedRectangle(cornerRadius: Theme.radiusKey))
                    }
                }
                .contentShape(Rectangle())
                .onHover { hover = $0 && enabled }
                .animation(.easeInOut(duration: 0.12), value: hover)
                .animation(.easeInOut(duration: 0.1), value: pressed)
        }
    }
}

/// The single primary action on a screen: the family's gold gradient.
struct DigPrimaryKeyStyle: ButtonStyle {

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.sans(12, .semibold))
            .foregroundStyle(Color(hex: 0x1A1D1F))
            .padding(.horizontal, 16)
            .frame(height: 32)
            .background(
                RoundedRectangle(cornerRadius: Theme.radiusKey)
                    .fill(configuration.isPressed ? Theme.primaryPressed : Theme.accent)
                    .overlay(Theme.primaryGradient.clipShape(RoundedRectangle(cornerRadius: Theme.radiusKey)))
            )
            .overlay(alignment: .top) {
                if configuration.isPressed {
                    Rectangle().fill(Color.black.opacity(0.18)).frame(height: 1)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.radiusKey))
                }
            }
            .contentShape(Rectangle())
    }
}

/// Instrument register label: mono, upper case, tracked.
struct InstrumentLabel: View {

    let text: String
    var color: Color = Theme.textTertiary

    var body: some View {
        Text(text.uppercased())
            .font(Theme.mono(10))
            .tracking(0.8)
            .foregroundStyle(color)
    }
}

/// Status chip used by the crate and the audition pane.
struct StatusChip: View {

    let text: String
    var color: Color = Theme.textTertiary

    var body: some View {
        Text(text.uppercased())
            .font(Theme.sans(10, .medium))
            .tracking(0.4)
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: Theme.radiusPad).fill(color.opacity(0.12)))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.radiusPad).strokeBorder(color.opacity(0.28), lineWidth: 1)
            )
    }
}

/// 28 pt search field with a leading magnifier, as in the reference's list column.
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
        .background(RoundedRectangle(cornerRadius: Theme.radiusKey).fill(Theme.bgControl))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.radiusKey).strokeBorder(Theme.border, lineWidth: 1)
        )
    }
}

/// A monogram avatar; artwork replaces it when the catalogue has a match.
struct Monogram: View {

    let text: String
    var size: CGFloat = 40
    var imageURL: URL?

    var body: some View {
        ZStack {
            Circle().fill(Theme.bgElevated)

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
        .overlay(Circle().strokeBorder(Theme.border, lineWidth: 1))
    }

    private var initials: some View {
        Text(text.prefix(2).uppercased())
            .font(Theme.sans(size * 0.33, .semibold))
            .foregroundStyle(Theme.textSecondary)
    }
}
