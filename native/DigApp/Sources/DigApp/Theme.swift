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

    static let bgCanvas = Color(hex: 0x1A1D1F)
    static let bgBase = Color(hex: 0x1C1E20)
    static let bgWorkspace = Color(hex: 0x202224)
    static let bgCard = Color(hex: 0x202224)
    static let bgElevated = Color(hex: 0x26292B)
    static let bgHover = Color(hex: 0x26292B)
    static let bgRowSelected = Color(hex: 0x2D3134)
    static let bgControl = Color(hex: 0x202224)
    static let bgControlHover = Color(hex: 0x2A2D30)
    static let bgWaveCanvas = Color(hex: 0x1A1D1F)

    static let border = Color(hex: 0x2C2F31)
    static let borderMedium = Color(hex: 0x3A3E40)
    static let borderSelected = Color(hex: 0xFFCD52).opacity(0.58)

    // MARK: - Ink

    static let textPrimary = Color(hex: 0xEEECE6)
    static let textSecondary = Color(hex: 0xB6BCB9)
    static let textTertiary = Color(hex: 0xA8AEAB)
    static let textMuted = Color(hex: 0x9AA19D)

    static let statusSaved = Color(hex: 0x8FBFAE)
    static let statusError = Color(hex: 0xD8938C)

    // MARK: - Accent

    static let accent = Color(hex: 0xFFCD52)
    static let accentHover = Color(hex: 0xFFE093)
    static let accentDeep = Color(hex: 0xBD902C)
    static let accentSoft = Color(hex: 0xFFCD52).opacity(0.12)
    static let primaryGradient = LinearGradient(
        colors: [Color(hex: 0xFFDC7D), Color(hex: 0xFFCB4C), Color(hex: 0xEEB735)],
        startPoint: .top, endPoint: .bottom
    )
    static let primaryPressed = Color(hex: 0xE9B841)

    // MARK: - Waveform

    static let waveGraphite = Color(hex: 0x4A4A4C)
    static let waveGraphitePeak = Color(hex: 0x737472)
    static let waveAmber = Color(hex: 0xFFCD52)

    // MARK: - Geometry

    static let radiusShell: CGFloat = 16
    static let radiusPanel: CGFloat = 8
    static let radiusRow: CGFloat = 8
    static let radiusKey: CGFloat = 6
    static let radiusPad: CGFloat = 3

    static let railWidth: CGFloat = 88
    static let railItemHeight: CGFloat = 72
    static let topStripHeight: CGFloat = 52
    static let listWidth: CGFloat = 400
    static let folderColumnWidth: CGFloat = 240
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
        Font(namedFont("IBM Plex Mono", size: size))
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
            NSLog("DigApp: font folder missing, falling back to system fonts")
            return
        }

        for file in files where file.pathExtension == "woff2" {
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
