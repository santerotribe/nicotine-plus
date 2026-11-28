// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import XCTest
@testable import TribeSeek

final class TribeSeekTests: XCTestCase {

    func testVirtualPathUsesOneBackslash() {
        XCTAssertEqual(VirtualPath.join(folder: "House\\Deep", name: "a.mp3"), "House\\Deep\\a.mp3")
        XCTAssertEqual(VirtualPath.join(folder: "", name: "a.mp3"), "a.mp3")
    }

    func testClockFormatsMinutesAndSeconds() {
        XCTAssertEqual(TimeFormat.clock(0), "0:00")
        XCTAssertEqual(TimeFormat.clock(65.4), "1:05")
        XCTAssertEqual(TimeFormat.clock(3725), "62:05")
    }

    func testGenericBinsInheritTheirCollection() {
        let bin = BrowserModel.FolderRow(
            name: "@@peer\\Albums\\Big Gold Dreams\\CD 4",
            count: 25,
            size: 550_400_000,
            audioFiles: 25,
            audioFormats: ["flac": 25],
            lossless: 25,
            seconds: 3_600
        )

        XCTAssertTrue(bin.isGeneric)
        XCTAssertEqual(bin.collectionTitle, "Big Gold Dreams")
        XCTAssertEqual(bin.qualityLabel, "FLAC 25")
        XCTAssertEqual(bin.losslessRatio, 1.0)

        let album = BrowserModel.FolderRow(
            name: "@@peer\\ZYX Italo\\Placebo [FLAC]",
            count: 10,
            size: 100,
            audioFiles: 8,
            audioFormats: ["flac": 8],
            lossless: 8,
            seconds: 100
        )

        XCTAssertFalse(album.isGeneric)
        XCTAssertEqual(album.collectionTitle, "ZYX Italo")
        XCTAssertEqual(album.losslessRatio, 1.0)
    }

    @MainActor
    func testSearchTabKnowsWhenItIsUnused() {
        let tab = SearchModel()

        XCTAssertTrue(tab.isEmptyTab)
        XCTAssertEqual(tab.title, "New search")

        tab.term = "  italo disco  "
        XCTAssertEqual(tab.title, "italo disco")

        tab.isSearching = true
        XCTAssertFalse(tab.isEmptyTab)

        tab.isSearching = false
        tab.token = 12
        XCTAssertFalse(tab.isEmptyTab)
    }

    func testAuditionPayloadDecodesSourceAndPeer() throws {

        let json = """
        {
          "id": "abc123",
          "username": "dj",
          "virtual_path": "House\\\\track.mp3",
          "folder": "House",
          "filename": "track.mp3",
          "size": 14488855,
          "duration": 361,
          "local_path": "",
          "kept": false,
          "track_id": "",
          "catalogue_state": "matched",
          "catalogue_error": "",
          "catalogue": [{
            "artist": "Ruggier", "title": "Long Ride", "label": "Ruggier - Long Ride",
            "album": "SLW - Single", "duration": 360, "score": 1.0, "source": "itunes",
            "preview_url": "https://example.test/p.m4a", "stream_url": "",
            "playback_url": "https://example.test/p.m4a", "store_url": "", "artwork": ""
          }],
          "peer": {
            "active": true, "status": "queued", "bytes": 0, "size": 14488855,
            "percent": 0.0, "queue_position": 1055, "partial_path": "",
            "finished_path": "", "complete": false, "error": ""
          },
          "source": {
            "kind": "catalogue", "url": "https://example.test/p.m4a",
            "bytes": 0, "total": 0, "complete": false
          }
        }
        """

        let state = try JSONDecoder().decode(AuditionState.self, from: Data(json.utf8))

        XCTAssertEqual(state.id, "abc123")
        XCTAssertEqual(state.folder, "House")
        XCTAssertEqual(state.catalogue.first?.score, 1.0)
        XCTAssertEqual(state.peer.queuePosition, 1055)
        XCTAssertEqual(state.source?.kind, .catalogue)
        XCTAssertEqual(state.source?.playableLocation, "https://example.test/p.m4a")
    }

    func testSearchResultsPageDecodesPrivateFlag() throws {

        let json = """
        {
          "token": 7, "total": 1, "offset": 0, "limit": 500,
          "results": [{
            "username": "dj", "virtual_path": "A\\\\b.mp3", "folder": "A", "filename": "b.mp3",
            "size": 1000, "bitrate": 320, "length": 200, "vbr": 0,
            "sample_rate": null, "bit_depth": null,
            "slot_available": false, "upload_speed": 1000,
            "queue_position": 4, "private": true
          }]
        }
        """

        let page = try JSONDecoder().decode(SearchResultsPage.self, from: Data(json.utf8))

        XCTAssertEqual(page.total, 1)
        XCTAssertTrue(page.results[0].privateShare)
        XCTAssertEqual(page.results[0].asFile.name, "b.mp3")
    }
}
