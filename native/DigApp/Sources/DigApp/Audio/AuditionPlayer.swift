// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import AVFoundation
import Foundation
import Observation

/// AVAudioEngine playback for auditioned files.
///
/// The engine hands us a location: a file on disk (our share, a kept download, a
/// peer's partial file) or a catalogue URL. Remote URLs are downloaded once, then
/// treated exactly like a file, so there is a single playback path with a real
/// frame clock for the waveform.
@MainActor
@Observable
final class AuditionPlayer {

    private let engine = AVAudioEngine()
    private let node = AVAudioPlayerNode()

    private var file: AVAudioFile?
    private var segmentStartSeconds: Double = 0

    private(set) var title = ""
    private(set) var badge = ""
    private(set) var location = ""
    private(set) var isPlaying = false
    private(set) var isLoading = false
    private(set) var isReady = false
    private(set) var errorText = ""
    private(set) var duration: Double = 0
    private(set) var peaks: [Float] = []
    private(set) var sampleRate: Double = 44_100

    var volume: Float = 0.9 {
        didSet { node.volume = volume }
    }

    private var loadGeneration = 0

    /// A file on disk that can be dragged out; nil for catalogue streams.
    var localFileURL: URL? {

        guard !location.hasPrefix("http://"), !location.hasPrefix("https://"), !location.isEmpty else {
            return nil
        }

        return FileManager.default.fileExists(atPath: location) ? URL(fileURLWithPath: location) : nil
    }

    init() {
        engine.attach(node)
    }

    // MARK: - Loading

    func load(location: String, title: String, badge: String, startAt: Double = 0) {

        let generation = loadGeneration + 1
        loadGeneration = generation

        self.title = title
        self.badge = badge
        self.location = location
        self.errorText = ""
        self.isLoading = true
        self.isReady = false
        self.stopNode()

        Task {
            do {
                let localURL = try await Self.localFile(for: location)

                guard generation == loadGeneration else { return }

                let audioFile = try AVAudioFile(forReading: localURL)
                let frames = audioFile.length
                let rate = audioFile.processingFormat.sampleRate

                guard frames > 0, rate > 0 else {
                    throw PlayerError.empty
                }

                self.file = audioFile
                self.duration = Double(frames) / rate
                self.sampleRate = rate
                self.isReady = true
                self.isLoading = false

                self.schedule(from: max(0, min(startAt, self.duration)))
                self.play()
                self.peaks = await PeaksExtractor.peaks(url: localURL, buckets: 1_200)

            } catch {
                guard generation == loadGeneration else { return }

                self.isLoading = false
                self.isReady = false
                self.errorText = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }

    // MARK: - Transport

    func toggle() {
        isPlaying ? pause() : play()
    }

    func play() {

        guard file != nil else { return }

        do {
            if !engine.isRunning {
                engine.prepare()
                try engine.start()
            }
        } catch {
            errorText = "Audio output failed: \(error.localizedDescription)"
            return
        }

        node.play()
        isPlaying = true
    }

    func pause() {
        node.pause()
        isPlaying = false
    }

    func stop() {
        stopNode()
        file = nil
        isReady = false
        isPlaying = false
        duration = 0
        peaks = []
        segmentStartSeconds = 0
    }

    func seek(to seconds: Double) {

        guard file != nil else { return }

        let clamped = max(0, min(seconds, duration - 0.05))
        let wasPlaying = isPlaying

        stopNode()
        schedule(from: clamped)

        if wasPlaying {
            play()
        }
    }

    func position() -> Double {

        guard let nodeTime = node.lastRenderTime,
              let playerTime = node.playerTime(forNodeTime: nodeTime) else {
            return segmentStartSeconds
        }

        let seconds = segmentStartSeconds + Double(playerTime.sampleTime) / playerTime.sampleRate
        return max(0, min(seconds, duration))
    }

    // MARK: - Internals

    private func schedule(from seconds: Double) {

        guard let file else { return }

        stopNode()

        let frame = AVAudioFramePosition(seconds * file.processingFormat.sampleRate)
        let remaining = AVAudioFrameCount(max(0, file.length - frame))

        guard remaining > 0 else { return }

        engine.disconnectNodeOutput(node)
        engine.connect(node, to: engine.mainMixerNode, format: file.processingFormat)
        node.scheduleSegment(file, startingFrame: frame, frameCount: remaining, at: nil)
        segmentStartSeconds = seconds
        node.volume = volume
    }

    private func stopNode() {
        node.stop()
        isPlaying = false
    }

    static func localFile(for location: String) async throws -> URL {

        if location.hasPrefix("http://") || location.hasPrefix("https://") {
            guard let url = URL(string: location) else { throw PlayerError.badURL }

            let (temporary, response) = try await URLSession.shared.download(from: url)

            guard (response as? HTTPURLResponse)?.statusCode ?? 200 < 400 else {
                throw PlayerError.downloadFailed
            }

            let folder = FileManager.default.temporaryDirectory.appendingPathComponent("DigApp-audio")
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

            let destination = folder.appendingPathComponent(UUID().uuidString)
                .appendingPathExtension(url.pathExtension.isEmpty ? "m4a" : url.pathExtension)

            try? FileManager.default.removeItem(at: destination)
            try FileManager.default.moveItem(at: temporary, to: destination)
            return destination
        }

        let url = URL(fileURLWithPath: location)

        guard FileManager.default.fileExists(atPath: url.path) else {
            throw PlayerError.missing(location)
        }

        return url
    }
}

enum PlayerError: LocalizedError {

    case empty
    case badURL
    case downloadFailed
    case missing(String)

    var errorDescription: String? {
        switch self {
        case .empty: "The file has no audio yet"
        case .badURL: "The catalogue returned an invalid URL"
        case .downloadFailed: "Could not download the catalogue preview"
        case .missing(let path): "Missing audio file: \(path)"
        }
    }
}

/// Waveform peaks, computed off the main actor from a fresh handle.
enum PeaksExtractor {

    static func peaks(url: URL, buckets: Int) async -> [Float] {

        await Task.detached(priority: .utility) {
            guard let file = try? AVAudioFile(forReading: url),
                  let buffer = AVAudioPCMBuffer(
                    pcmFormat: file.processingFormat,
                    frameCapacity: 65_536)
            else {
                return []
            }

            let total = file.length
            let framesPerBucket = max(1, Int(total) / max(1, buckets))
            var result: [Float] = []
            var accumulated: Float = 0
            var count = 0

            while file.framePosition < total {
                do {
                    try file.read(into: buffer)
                } catch {
                    break
                }

                guard let channel = buffer.floatChannelData?[0] else { break }

                for index in 0..<Int(buffer.frameLength) {
                    accumulated = max(accumulated, abs(channel[index]))
                    count += 1

                    if count >= framesPerBucket {
                        result.append(accumulated)
                        accumulated = 0
                        count = 0
                    }
                }
            }

            if count > 0 {
                result.append(accumulated)
            }

            // Normalise so the drawing uses the full height without a scale guess.
            let peak = result.max() ?? 0

            if peak > 0 {
                result = result.map { $0 / peak }
            }

            return result
        }.value
    }
}
