// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import Foundation

/// One event from `GET /events`.
struct EngineEvent {

    let type: String
    let data: Data

    func decode<T: Decodable>(_ type: T.Type, using decoder: JSONDecoder = .engine) -> T? {
        try? decoder.decode(type, from: data)
    }
}

extension JSONDecoder {

    static var engine: JSONDecoder {
        let decoder = JSONDecoder()
        return decoder
    }
}

enum EngineError: LocalizedError {

    case badStatus(Int, String)
    case unreachable(String)

    var errorDescription: String? {
        switch self {
        case .badStatus(let code, let message): "Engine answered \(code): \(message)"
        case .unreachable(let message): "Engine unreachable: \(message)"
        }
    }

    /// The one error worth retrying by itself: the engine is up, Soulseek is not.
    var isNotLoggedIn: Bool {
        if case .badStatus(let code, let message) = self {
            return code == 409 || message.lowercased().contains("not logged in")
        }

        return false
    }
}

/// HTTP + Server-Sent Events against the local engine.
struct EngineClient {

    let baseURL: URL
    let token: String

    private let session: URLSession
    private let decoder = JSONDecoder.engine

    init(baseURL: URL, token: String) {
        self.baseURL = baseURL
        self.token = token

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.waitsForConnectivity = false
        configuration.httpAdditionalHeaders = ["Accept": "application/json"]
        self.session = URLSession(configuration: configuration)
    }

    // MARK: - Requests

    private func request(_ path: String, method: String = "GET", body: Data? = nil) -> URLRequest {

        // Keep the query string intact: appendingPathComponent() would escape
        // the "?" and turn the query into part of the path.
        let root = baseURL.absoluteString.hasSuffix("/") ? baseURL.absoluteString : baseURL.absoluteString + "/"
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path

        guard let url = URL(string: root + trimmed) else {
            preconditionFailure("Bad engine path: \(path)")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")

        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        return request
    }

    private func send(_ request: URLRequest) async throws -> Data {
        do {
            let (data, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0

            guard (200..<300).contains(status) else {
                // The API answers {"error": "..."} — surface that, not raw JSON.
                let body = String(data: data, encoding: .utf8) ?? "no body"
                let detail = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                throw EngineError.badStatus(status, detail?["error"] as? String ?? body)
            }

            return data

        } catch let error as EngineError {
            throw error

        } catch {
            throw EngineError.unreachable(error.localizedDescription)
        }
    }

    func get<T: Decodable>(_ path: String, as type: T.Type = T.self) async throws -> T {
        try decoder.decode(T.self, from: try await send(request(path)))
    }

    func post<T: Decodable>(_ path: String, body: Encodable? = nil, as type: T.Type = T.self) async throws -> T {
        let data: Data?

        if let body {
            data = try JSONEncoder().encode(AnyEncodable(body))
        } else {
            data = nil
        }

        return try decoder.decode(T.self, from: try await send(request(path, method: "POST", body: data)))
    }

    @discardableResult
    func delete<T: Decodable>(_ path: String, as type: T.Type = T.self) async throws -> T {
        try decoder.decode(T.self, from: try await send(request(path, method: "DELETE")))
    }

    /// Ask the engine to log in again. After a relogin elsewhere it stops
    /// retrying on purpose, until a client says the other session is gone.
    func reconnect() async throws {
        struct Response: Decodable {
            let connected: Bool?
            let connecting: Bool?
        }

        _ = try await post("/login", as: Response.self)
    }

    func health() async throws -> EngineHealth {
        try decoder.decode(EngineHealth.self, from: try await send(request("/health")))
    }

    func state() async throws -> EngineState {
        try await get("/state")
    }

    // MARK: - Browse

    func browse(user: String) async throws {
        struct Response: Decodable { let requested: String }
        _ = try await post("/users/\(escape(user))/browse", as: Response.self)
    }

    func summary(user: String) async throws -> BrowseSummary {
        try await get("/users/\(escape(user))/summary")
    }

    func folders(user: String, offset: Int = 0, limit: Int = 200) async throws -> FolderPage {
        try await get("/users/\(escape(user))/folders?offset=\(offset)&limit=\(limit)")
    }

    func files(user: String, folder: String, offset: Int = 0, limit: Int = 500) async throws -> FilePage {
        try await get("/users/\(escape(user))/files?folder=\(escape(folder))&offset=\(offset)&limit=\(limit)")
    }

    // MARK: - Downloads / crate

    func downloads() async throws -> DownloadsPage {
        try await get("/downloads?limit=500")
    }

    func crate(kind: String? = nil) async throws -> CratePage {
        if let kind, let escaped = kind.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            return try await get("/crate?kind=\(escaped)")
        }

        return try await get("/crate")
    }

    func deleteCrateTrack(id: String) async throws {
        struct Response: Decodable { let removed: String }
        _ = try await delete("/crate/\(escape(id))", as: Response.self)
    }

    func setCrateKind(id: String, kind: String) async throws {
        struct Body: Encodable { let kind: String }
        struct Response: Decodable { let track: CrateTrack }
        _ = try await post("/crate/\(escape(id))/kind", body: Body(kind: kind), as: Response.self)
    }

    // MARK: - Search

    func startSearch(term: String) async throws -> SearchSummary {
        struct Body: Encodable { let term: String; let mode = "global" }
        return try await post("/search", body: Body(term: term), as: SearchSummary.self)
    }

    func searchUsers(token: Int, offset: Int = 0, limit: Int = 100) async throws -> SearchUsersPage {
        try await get("/search/\(token)/users?offset=\(offset)&limit=\(limit)")
    }

    func searchResults(token: Int, offset: Int = 0, limit: Int = 500) async throws -> SearchResultsPage {
        try await get("/search/\(token)/results?offset=\(offset)&limit=\(limit)")
    }

    func stopSearch(token: Int) async throws {
        struct Response: Decodable { let stopped: Int }
        _ = try await post("/search/\(token)/stop", as: Response.self)
    }

    /// Stop the search and drop its results from the engine's store.
    func deleteSearch(token: Int) async throws {
        struct Response: Decodable { let stopped: Int }
        _ = try await delete("/search/\(token)", as: Response.self)
    }

    func separateCrateTrack(id: String) async throws {
        struct Response: Decodable { let separating: String }
        _ = try await post("/crate/\(escape(id))/separate", as: Response.self)
    }

    // MARK: - Audition

    struct AuditionRequest: Encodable {

        let username: String
        let virtualPath: String
        let size: Int64
        let duration: Double
        let attributes: Attributes

        struct Attributes: Encodable {
            let bitrate: Int?
            let length: Int?
            let vbr: Int?
            let sampleRate: Int?
            let bitDepth: Int?

            enum CodingKeys: String, CodingKey {
                case bitrate, length, vbr
                case sampleRate = "sample_rate"
                case bitDepth = "bit_depth"
            }
        }

        enum CodingKeys: String, CodingKey {
            case username, size, duration, attributes
            case virtualPath = "virtual_path"
        }
    }

    func startAudition(_ body: AuditionRequest) async throws -> AuditionState {
        try await post("/audition", body: body, as: AuditionState.self)
    }

    func audition(id: String) async throws -> AuditionState {
        try await get("/audition/\(escape(id))")
    }

    func keepAudition(id: String, kind: String = "sample") async throws -> CrateTrack {
        struct Body: Encodable { let kind: String }
        struct Response: Decodable { let track: CrateTrack }
        let response: Response = try await post(
            "/audition/\(escape(id))/keep", body: Body(kind: kind), as: Response.self)
        return response.track
    }

    func closeAudition(id: String) async throws {
        struct Response: Decodable { let closed: String }
        _ = try await delete("/audition/\(escape(id))", as: Response.self)
    }

    // MARK: - Events

    /// Stream `/events`. Yields `hello`, `browse`, `audition`, `crate`, `transfers`.
    func events() -> AsyncThrowingStream<EngineEvent, Error> {

        AsyncThrowingStream { continuation in

            let task = Task {
                do {
                    var request = request("/events")
                    request.timeoutInterval = 3600
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                    let (bytes, response) = try await session.bytes(for: request)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    NSLog("TribeSeek: event stream opened with %d", status)

                    guard status == 200 else {
                        continuation.finish(throwing: EngineError.badStatus(status, "event stream refused"))
                        return
                    }

                    var eventType = "message"

                    // Our server writes one data line per event, so every data
                    // line is a complete event. (AsyncLineSequence is not
                    // guaranteed to surface the blank separator line.)
                    for try await line in bytes.lines {
                        if line.hasPrefix(":") {
                            continue
                        }

                        if line.hasPrefix("event: ") {
                            eventType = String(line.dropFirst(7))
                            continue
                        }

                        if line.hasPrefix("data: ") {
                            let payload = String(line.dropFirst(6))
                            continuation.yield(EngineEvent(type: eventType, data: Data(payload.utf8)))
                            eventType = "message"
                            continue
                        }

                        if line.isEmpty {
                            eventType = "message"
                        }
                    }

                    continuation.finish()

                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func escape(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }
}

/// Type erasure so `post` can take any Encodable body.
struct AnyEncodable: Encodable {

    private let encodeClosure: (Encoder) throws -> Void

    init(_ wrapped: Encodable) {
        encodeClosure = { encoder in try wrapped.encode(to: encoder) }
    }

    func encode(to encoder: Encoder) throws {
        try encodeClosure(encoder)
    }
}
