// swift-tools-version: 6.0
// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import PackageDescription

let package = Package(
    name: "TribeSeek",
    platforms: [.macOS("14.0")],
    products: [
        .executable(name: "TribeSeek", targets: ["TribeSeek"])
    ],
    targets: [
        .executableTarget(
            name: "TribeSeek",
            resources: [.copy("Resources/Fonts")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "TribeSeekTests",
            dependencies: ["TribeSeek"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
