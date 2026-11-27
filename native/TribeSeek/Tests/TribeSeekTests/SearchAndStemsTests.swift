// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import XCTest
@testable import TribeSeek

final class SearchAndStemsTests: XCTestCase {

    private func result(_ username: String, _ name: String) -> SearchResultRow {
        SearchResultRow(
            username: username,
            virtualPath: "A\\" + name,
            folder: "A",
            filename: name,
            size: 1_000,
            bitrate: 320,
            length: 200,
            vbr: 0,
            sampleRate: 44_100,
            bitDepth: 16,
            slotAvailable: true,
            uploadSpeed: 1_000,
            queuePosition: 0,
            privateShare: false
        )
    }

    @MainActor
    func testSearchGroupsKeepFirstAppearanceOrder() {

        let model = SearchModel()
        model.results = [
            result("beta", "b1.mp3"),
            result("alpha", "a1.mp3"),
            result("beta", "b2.mp3"),
        ]

        XCTAssertEqual(model.groups.map(\.username), ["beta", "alpha"])
        XCTAssertEqual(model.groups[0].results.count, 2)
        XCTAssertEqual(model.groups[1].results.count, 1)
    }

    func testCrateTrackDecodesStems() throws {

        let json = """
        {
          "id": "t1", "username": "dj", "filename": "x.aif", "virtual_path": "A\\\\x.aif",
          "status": "ready", "bpm": 124.0, "local_path": "/tmp/x.aif",
          "stems": {"drums": "/tmp/drums.wav", "bass": "/tmp/bass.wav"},
          "als_path": "", "error": ""
        }
        """

        let track = try JSONDecoder().decode(CrateTrack.self, from: Data(json.utf8))

        XCTAssertEqual(track.stems.count, 2)
        XCTAssertEqual(track.stems["drums"], "/tmp/drums.wav")
        XCTAssertEqual(track.bpm, 124.0)
    }

    func testStemExistenceFollowsTheDisk() throws {

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("stem-\(UUID().uuidString).wav")
        try Data([0x00, 0x01]).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }

        XCTAssertTrue(StemFile(name: "drums", path: url.path).exists)
        XCTAssertFalse(StemFile(name: "bass", path: url.path + ".missing").exists)
    }
}
