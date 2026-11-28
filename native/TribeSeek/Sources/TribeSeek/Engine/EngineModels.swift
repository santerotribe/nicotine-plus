// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation

/// Raw shapes the engine returns. No formatting happens here: bytes stay bytes,
/// seconds stay seconds, exactly as docs/ENGINE-API.md promises.

struct EngineState: Decodable {

    let username: String?
    let status: String?
    let privilegesSeconds: Int?
    let downloads: Int?
    let browsedUsers: [String]?
    let eventSubscribers: Int?

    enum CodingKeys: String, CodingKey {
        case username, status, downloads
        case privilegesSeconds = "privileges_seconds"
        case browsedUsers = "browsed_users"
        case eventSubscribers = "event_subscribers"
    }

    var isLoggedIn: Bool { connection == .online && username?.isEmpty == false }
    var privilegesDays: Int { (privilegesSeconds ?? 0) / 86_400 }

    enum Connection: String {
        case offline, connecting, online
    }

    var connection: Connection {
        switch status {
        case "2": .online
        case "1": .connecting
        default: .offline
        }
    }
}

struct EngineHealth: Decodable {
    let ok: Bool
    let version: String
    let loggedIn: Bool
    let username: String?

    enum CodingKeys: String, CodingKey {
        case ok, version, username
        case loggedIn = "logged_in"
    }
}

struct BrowseSummary: Decodable {
    let username: String
    let folders: Int
    let files: Int
    let sharedSize: Int64
    let messages: Int

    enum CodingKeys: String, CodingKey {
        case username, folders, files, messages
        case sharedSize = "shared_size"
    }
}

struct FolderPage: Decodable {
    let total: Int
    let offset: Int
    let limit: Int
    let folders: [FolderInfo]
}

struct FolderInfo: Decodable {
    let name: String
    let files: Int
    let size: Int64
    let audioFiles: Int
    let audioFormats: [String: Int]
    let lossless: Int
    let duration: Double

    enum CodingKeys: String, CodingKey {
        case name, files, size, lossless, duration
        case audioFiles = "audio_files"
        case audioFormats = "audio_formats"
    }
}

struct FilePage: Decodable {
    let total: Int
    let offset: Int
    let limit: Int
    let files: [SharedFileRow]
}

struct SharedFileRow: Decodable, Identifiable, Hashable {

    let name: String
    let size: Int64
    let bitrate: Int?
    let length: Int?
    let vbr: Int?
    let sampleRate: Int?
    let bitDepth: Int?

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name, size, bitrate, length, vbr
        case sampleRate = "sample_rate"
        case bitDepth = "bit_depth"
    }
}

struct TransferRow: Decodable, Identifiable {

    let username: String
    let virtualPath: String
    let filename: String
    let folder: String
    let size: Int64
    let transferred: Int64
    let status: String
    let queuePosition: Int
    let speed: Double
    let percent: Double

    var id: String { username + "/" + virtualPath }

    enum CodingKeys: String, CodingKey {
        case username, filename, folder, size, transferred, status, speed, percent
        case virtualPath = "virtual_path"
        case queuePosition = "queue_position"
    }
}

struct DownloadsPage: Decodable {
    let total: Int
    let downloads: [TransferRow]
}

struct CrateTrack: Decodable, Identifiable {

    let id: String
    let username: String
    let filename: String
    let virtualPath: String
    let kind: String
    let status: String
    let bpm: Double?
    let addedAt: Double?
    let localPath: String?
    let alsPath: String?
    let error: String?
    let stems: [String: String]

    enum CodingKeys: String, CodingKey {
        case id, username, filename, kind, status, bpm, error, stems
        case addedAt = "added_at"
        case virtualPath = "virtual_path"
        case localPath = "local_path"
        case alsPath = "als_path"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        username = try container.decode(String.self, forKey: .username)
        filename = try container.decode(String.self, forKey: .filename)
        virtualPath = try container.decode(String.self, forKey: .virtualPath)
        kind = try container.decodeIfPresent(String.self, forKey: .kind) ?? "sample"
        status = try container.decode(String.self, forKey: .status)
        bpm = try container.decodeIfPresent(Double.self, forKey: .bpm)
        localPath = try container.decodeIfPresent(String.self, forKey: .localPath)
        alsPath = try container.decodeIfPresent(String.self, forKey: .alsPath)
        error = try container.decodeIfPresent(String.self, forKey: .error)
        stems = try container.decodeIfPresent([String: String].self, forKey: .stems) ?? [:]
        addedAt = try container.decodeIfPresent(Double.self, forKey: .addedAt)
    }

    init(id: String, username: String, filename: String, virtualPath: String,
         kind: String = "sample", status: String = "kept", bpm: Double? = nil,
         localPath: String? = nil, alsPath: String? = nil, error: String? = nil,
         stems: [String: String] = [:], addedAt: Double? = nil) {
        self.id = id
        self.username = username
        self.filename = filename
        self.virtualPath = virtualPath
        self.kind = kind
        self.status = status
        self.bpm = bpm
        self.localPath = localPath
        self.alsPath = alsPath
        self.error = error
        self.stems = stems
        self.addedAt = addedAt
    }
}

/// One separated stem on disk.
struct StemFile: Identifiable, Hashable {

    let name: String
    let path: String

    var id: String { name }
    var url: URL { URL(fileURLWithPath: path) }
    var exists: Bool { FileManager.default.fileExists(atPath: path) }
}

struct RolodexEntry: Decodable, Identifiable {

    let peer: String
    let virtualPath: String
    let folder: String
    let filename: String
    let kind: String
    let foundBy: String
    let addedAt: Double

    var id: String { peer + "/" + virtualPath }

    enum CodingKeys: String, CodingKey {
        case peer, folder, filename, kind
        case virtualPath = "virtual_path"
        case foundBy = "found_by"
        case addedAt = "added_at"
    }
}

struct RolodexPage: Decodable {
    let path: String
    let member: String
    let entries: [RolodexEntry]
}

struct RendererReadiness: Decodable {
    let ready: Bool
    let message: String
}

struct SettingsPayload: Decodable {

    let workDir: String
    let outputDir: String
    let exportDir: String
    let rolodexPath: String
    let memberName: String
    let renderer: String
    let preset: String
    let mvsepSepType: String
    let pcURL: String
    let previewCacheMB: Int
    let warpStems: Bool
    let openAfterBuild: Bool
    let warpMode: String
    let presets: [String]
    let warpModes: [String]
    let rendererAvailable: [String: RendererReadiness]
    let mvsepTokenSet: Bool
    let pcTokenSet: Bool

    enum CodingKeys: String, CodingKey {
        case renderer, preset, presets
        case workDir = "work_dir"
        case outputDir = "output_dir"
        case exportDir = "export_dir"
        case rolodexPath = "rolodex_path"
        case memberName = "member_name"
        case mvsepSepType = "mvsep_sep_type"
        case pcURL = "pc_url"
        case previewCacheMB = "preview_cache_mb"
        case warpStems = "warp_stems"
        case openAfterBuild = "open_after_build"
        case warpMode = "warp_mode"
        case warpModes = "warp_modes"
        case rendererAvailable = "renderer_available"
        case mvsepTokenSet = "mvsep_token_set"
        case pcTokenSet = "pc_token_set"
    }
}

struct SettingsPatch: Encodable {

    var workDir: String?
    var outputDir: String?
    var exportDir: String?
    var rolodexPath: String?
    var memberName: String?
    var renderer: String?
    var preset: String?
    var mvsepSepType: String?
    var pcURL: String?
    var previewCacheMB: Int?
    var warpStems: Bool?
    var openAfterBuild: Bool?
    var warpMode: String?
    var mvsepToken: String?
    var pcToken: String?

    enum CodingKeys: String, CodingKey {
        case renderer, preset
        case workDir = "work_dir"
        case outputDir = "output_dir"
        case exportDir = "export_dir"
        case rolodexPath = "rolodex_path"
        case memberName = "member_name"
        case mvsepSepType = "mvsep_sep_type"
        case pcURL = "pc_url"
        case previewCacheMB = "preview_cache_mb"
        case warpStems = "warp_stems"
        case openAfterBuild = "open_after_build"
        case warpMode = "warp_mode"
        case mvsepToken = "mvsep_token"
        case pcToken = "pc_token"
    }

    init(workDir: String? = nil, outputDir: String? = nil, exportDir: String? = nil,
         rolodexPath: String? = nil, memberName: String? = nil, renderer: String? = nil,
         preset: String? = nil, mvsepSepType: String? = nil, pcURL: String? = nil,
         previewCacheMB: Int? = nil, warpStems: Bool? = nil, openAfterBuild: Bool? = nil,
         warpMode: String? = nil, mvsepToken: String? = nil, pcToken: String? = nil) {
        self.workDir = workDir
        self.outputDir = outputDir
        self.exportDir = exportDir
        self.rolodexPath = rolodexPath
        self.memberName = memberName
        self.renderer = renderer
        self.preset = preset
        self.mvsepSepType = mvsepSepType
        self.pcURL = pcURL
        self.previewCacheMB = previewCacheMB
        self.warpStems = warpStems
        self.openAfterBuild = openAfterBuild
        self.warpMode = warpMode
        self.mvsepToken = mvsepToken
        self.pcToken = pcToken
    }
}

struct UserStatusRow: Decodable {
    let username: String
    let status: String
}

struct CratePage: Decodable {
    let total: Int
    let tracks: [CrateTrack]
}

struct SearchSummary: Decodable, Identifiable {

    let token: Int
    let term: String
    let mode: String
    let total: Int
    let users: Int
    let created: Int?

    var id: Int { token }

    enum CodingKeys: String, CodingKey {
        case token, term, mode, total, users
        case created = "created_at"
    }
}

struct SearchUsersPage: Decodable {
    let total: Int
    let users: [SearchUser]
}

struct SearchUser: Decodable, Identifiable {

    let username: String
    let files: Int
    let folders: Int
    let totalSize: Int64
    let slotAvailable: Bool
    let uploadSpeed: Int
    let queuePosition: Int

    var id: String { username }

    enum CodingKeys: String, CodingKey {
        case username, files, folders
        case totalSize = "total_size"
        case slotAvailable = "slot_available"
        case uploadSpeed = "upload_speed"
        case queuePosition = "queue_position"
    }
}

// MARK: - Audition

struct AuditionState: Decodable {

    let id: String
    let username: String
    let virtualPath: String
    let folder: String
    let filename: String
    let size: Int64
    let duration: Double
    let localPath: String
    let kept: Bool
    let trackId: String
    let catalogueState: String
    let catalogueError: String
    let catalogue: [CatalogueMatch]
    let peer: PeerState
    let source: AuditionSource?

    enum CodingKeys: String, CodingKey {
        case id, username, folder, filename, size, duration, kept, catalogue, peer, source
        case virtualPath = "virtual_path"
        case localPath = "local_path"
        case trackId = "track_id"
        case catalogueState = "catalogue_state"
        case catalogueError = "catalogue_error"
    }
}

struct CatalogueMatch: Decodable, Identifiable {

    let artist: String
    let title: String
    let label: String
    let album: String
    let duration: Double
    let score: Double
    let source: String
    let previewURL: String
    let streamURL: String
    let artwork: String

    var id: String { label + source }
    var artworkURL: URL? { URL(string: artwork) }
    var playableURL: String { previewURL.isEmpty ? streamURL : previewURL }

    enum CodingKeys: String, CodingKey {
        case artist, title, label, album, duration, score, source, artwork
        case previewURL = "preview_url"
        case streamURL = "stream_url"
    }
}

struct PeerState: Decodable {

    let active: Bool
    let status: String
    let bytes: Int64
    let size: Int64
    let percent: Double
    let queuePosition: Int
    let partialPath: String
    let finishedPath: String
    let complete: Bool
    let error: String

    enum CodingKeys: String, CodingKey {
        case active, status, bytes, size, percent, complete, error
        case queuePosition = "queue_position"
        case partialPath = "partial_path"
        case finishedPath = "finished_path"
    }
}

struct AuditionSource: Decodable {

    enum Kind: String, Decodable {
        case local, peer, catalogue
    }

    let kind: Kind
    let path: String?
    let url: String?
    /// Absent for a local file: there is nothing to fetch.
    let bytes: Int64?
    let total: Int64?
    let complete: Bool

    /// Something the audio player can open: a file on disk or a remote URL.
    var playableLocation: String? {
        if let path, !path.isEmpty { return path }
        if let url, !url.isEmpty { return url }
        return nil
    }
}
