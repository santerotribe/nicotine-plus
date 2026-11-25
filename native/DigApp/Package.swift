// swift-tools-version: 6.0
// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import PackageDescription

let package = Package(
    name: "DigApp",
    platforms: [.macOS("14.0")],
    products: [
        .executable(name: "DigApp", targets: ["DigApp"])
    ],
    targets: [
        .executableTarget(
            name: "DigApp",
            resources: [.copy("Resources/Fonts")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "DigAppTests",
            dependencies: ["DigApp"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
