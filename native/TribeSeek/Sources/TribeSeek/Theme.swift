// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AppKit
import CoreText
import SwiftUI

/// The family's tokens, ported from arcaNative's Theme.swift (values, not code).
///
/// Two registers, one surface ladder, hairlines instead of shadows, and a single
/// gold accent. See docs/UI-DIRECTION.md for the reasoning.
enum Theme {

    // MARK: - Surfaces

    static var bgCanvas: Color { Palette.shade(0x1A1D1F, 0x0B0B0D) }
    static var bgBase: Color { Palette.shade(0x1C1E20, 0x101012) }
    static var bgWorkspace: Color { Palette.shade(0x202224, 0x151517) }
    static var bgCard: Color { Palette.shade(0x202224, 0x19191C) }
    static var bgElevated: Color { Palette.shade(0x26292B, 0x202023) }
    static var bgHover: Color { Palette.shade(0x26292B, 0x202023) }
    static var bgRowSelected: Color { Palette.shade(0x2D3134, 0x26262A) }
    static var bgControl: Color { Palette.shade(0x202224, 0x19191C) }
    static var bgControlHover: Color { Palette.shade(0x2A2D30, 0x222226) }
    static var bgWaveCanvas: Color { Palette.shade(0x1A1D1F, 0x0B0B0D) }

    static var border: Color { Palette.shade(0x2C2F31, 0x242428) }
    static var borderMedium: Color { Palette.shade(0x3A3E40, 0x34343A) }
    static var borderSelected: Color { accent.opacity(0.58) }

    // MARK: - Ink

    static var textPrimary: Color { Palette.shade(0xEEECE6, 0xF7F4EF) }
    static var textSecondary: Color { Palette.shade(0xB6BCB9, 0xC2C2C1) }
    static var textTertiary: Color { Palette.shade(0xA8AEAB, 0xA3A3A3) }
    static var textMuted: Color { Palette.shade(0x9AA19D, 0x8C8B90) }

    static var statusSaved: Color { Palette.shade(0x8FBFAE, 0x93BFA6) }
    static var statusError: Color { Palette.shade(0xD8938C, 0xD08A84) }

    // MARK: - Accent

    static var accent: Color { Palette.shade(0xFFCD52, 0xD4A54A) }
    static var accentHover: Color { Palette.shade(0xFFE093, 0xE6BE6E) }
    static var accentDeep: Color { Palette.shade(0xBD902C, 0xA87C2E) }
    static var accentSoft: Color { accent.opacity(0.12) }
    static var primaryGradient: LinearGradient {
        LinearGradient(
            colors: Palette.active == .suno
                ? [Color(hex: 0xEFD6A2), Color(hex: 0xD4A54A), Color(hex: 0xB08434)]
                : [Color(hex: 0xFFDC7D), Color(hex: 0xFFCB4C), Color(hex: 0xEEB735)],
            startPoint: .top, endPoint: .bottom
        )
    }
    static var primaryPressed: Color { Palette.shade(0xE9B841, 0xC2953C) }

    // MARK: - Waveform

    static var waveGraphite: Color { Palette.shade(0x4A4A4C, 0x3A3A40) }
    static var waveGraphitePeak: Color { Palette.shade(0x737472, 0x74747C) }
    static var waveAmber: Color { accent }

    // MARK: - Geometry

    static let radiusShell: CGFloat = 16
    static let radiusPanel: CGFloat = 8
    static let radiusRow: CGFloat = 8
    static let radiusKey: CGFloat = 6
    static let radiusPad: CGFloat = 3

    static let railWidth: CGFloat = 88
    static let railItemHeight: CGFloat = 72
    static let topStripHeight: CGFloat = 66
    static let listWidth: CGFloat = 400
    static let folderColumnWidth: CGFloat = 300
    static let rowHeight: CGFloat = 48
    static let transportHeight: CGFloat = 48
    static let keyHeight: CGFloat = 28
    static let instrumentKeyHeight: CGFloat = 30

    // MARK: - Type

    /// Manrope is one variable file whose Core Text family resolves as
    /// "Manrope ExtraLight", so each weight goes by its own instance name.
    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        Font(sansFont(size, weight))
    }

    static func mono(_ size: CGFloat) -> Font {
        Font(namedFont("IBMPlexMono-Regular", size: size))
    }

    /// Readouts carry more weight than labels: Plex Mono Medium when the extra
    /// face is registered, the regular face otherwise.
    static func monoStrong(_ size: CGFloat) -> Font {
        Font(namedFont("IBMPlexMono-Medium", size: size))
    }

    static func sansFont(_ size: CGFloat, _ weight: Font.Weight = .regular) -> CTFont {
        let key = FontKey(name: manropeName(weight), size: size)

        if let font = fontCache.withLock({ $0[key] }) {
            return font
        }

        let font = makeFont(key.name, size: size)

        if size * 2 == (size * 2).rounded() {
            fontCache.withLock { $0[key] = font }
        }

        return font
    }

    private struct FontKey: Hashable {
        let name: String
        let size: CGFloat
    }

    private static let fontCache = Mutex<[FontKey: CTFont]>([:])

    /// Core Text names the bundled mono faces "IBMPlexMono-Regular" and
    /// "IBMPlexMono-Medium"; the family name alone does not resolve, and a
    /// silent fallback would quietly render SF Mono instead.
    private static func namedFont(_ name: String, size: CGFloat) -> NSFont {
        NSFont(name: name, size: size) ?? NSFont.monospacedSystemFont(ofSize: size, weight: .regular)
    }

    private static func makeFont(_ name: String, size: CGFloat) -> CTFont {
        let attributes: [CFString: Any] = [
            kCTFontNameAttribute: name,
            kCTFontFeatureSettingsAttribute: [
                [kCTFontOpenTypeFeatureTag: "cv11", kCTFontOpenTypeFeatureValue: 1],
                [kCTFontOpenTypeFeatureTag: "ss01", kCTFontOpenTypeFeatureValue: 1]
            ]
        ]
        return CTFontCreateWithFontDescriptor(
            CTFontDescriptorCreateWithAttributes(attributes as CFDictionary), size, nil)
    }

    static func manropeName(_ weight: Font.Weight) -> String {
        switch weight {
        case .ultraLight, .thin: "Manrope-ExtraLight"
        case .light: "Manrope-Light"
        case .medium: "Manrope-Medium"
        case .semibold: "Manrope-SemiBold"
        case .bold: "Manrope-Bold"
        case .heavy, .black: "Manrope-ExtraBold"
        default: "Manrope-Regular"
        }
    }

    /// Register the bundled woff2 files for this process. Called once at launch.
    static func registerFonts() {
        guard let folder = Bundle.module.url(forResource: "Fonts", withExtension: nil),
              let files = try? FileManager.default.contentsOfDirectory(
                at: folder, includingPropertiesForKeys: nil)
        else {
            NSLog("TribeSeek: font folder missing, falling back to system fonts")
            return
        }

        for file in files where file.pathExtension == "woff2" || file.pathExtension == "ttf" {
            var error: Unmanaged<CFError>?
            CTFontManagerRegisterFontsForURL(file as CFURL, .process, &error)
        }

        fontCache.withLock { $0.removeAll() }
    }
}

// MARK: - Small concurrency helper

/// A tiny lock wrapper so the font cache can be a plain static without
/// pulling in the whole Synchronization module.
final class Mutex<Value>: @unchecked Sendable {

    private var value: Value
    private let lock = NSLock()

    init(_ value: Value) { self.value = value }

    func withLock<Result>(_ body: (inout Value) throws -> Result) rethrows -> Result {
        lock.lock()
        defer { lock.unlock() }
        return try body(&value)
    }
}

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}
