// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Two palettes, one structure.
///
/// `arca` is the family graphite with a lemon gold accent. `suno` borrows the
/// deeper black and antique gold of Suno's UI (their dumbo-50 #101012 base and
/// the #C4A670/#D4A54A metallics), which reads warmer and quieter.
enum Skin: String {

    case arca
    case suno

    /// Suno's palette is the default; `DIG_SKIN=arca` brings back the graphite
    /// and lemon gold the client shipped with.
    static let active: Skin = {
        let raw = ProcessInfo.processInfo.environment["DIG_SKIN"] ?? ""
        return Skin(rawValue: raw) ?? .suno
    }()
}

enum Palette {

    static var active: Skin { Skin.active }

    /// Pick the token for the active palette.
    static func shade(_ arca: UInt32, _ suno: UInt32) -> Color {
        Color(hex: active == .suno ? suno : arca)
    }
}
