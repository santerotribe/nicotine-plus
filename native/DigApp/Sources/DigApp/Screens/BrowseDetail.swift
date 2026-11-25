// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Detail for Browse: the peer's folders and files, Enter to audition.
struct BrowseDetail: View {

    @Bindable var model: AppModel

    @State private var selectedFile: String?
    @FocusState private var filesFocused: Bool

    var body: some View {
        Group {
            if let user = model.browse.selectedUser {
                content(user: user)
            } else {
                EmptyStatePane(
                    symbol: "square.stack",
                    title: "Open a peer",
                    body: "Pick a name on the left or type a Soulseek username to browse their shares. Enter auditions the selected file; nothing is downloaded until you keep it."
                )
            }
        }
        .background(Theme.bgWorkspace)
    }

    private func content(user: String) -> some View {

        VStack(spacing: 0) {
            header(user: user)
            Divider().overlay(Theme.border)

            HStack(spacing: 0) {
                folderList
                    .frame(width: Theme.folderColumnWidth)

                Divider().overlay(Theme.border)

                fileList
            }
        }
    }

    private func header(user: String) -> some View {

        HStack(spacing: 12) {
            Monogram(text: user, size: 44)

            VStack(alignment: .leading, spacing: 3) {
                Text(user)
                    .font(Theme.sans(15, .semibold))
                    .foregroundStyle(Theme.textPrimary)

                if let summary = model.browse.summary {
                    HStack(spacing: 10) {
                        InstrumentLabel(text: "\(summary.files) FILES")
                        InstrumentLabel(text: "\(summary.folders) FOLDERS")
                        InstrumentLabel(text: size(summary.sharedSize))
                    }
                } else {
                    InstrumentLabel(text: model.browse.isBrowsing ? "BROWSING…" : "NO SUMMARY")
                }
            }

            Spacer()

            Button("Refresh") {
                Task { await model.browse.browse(user: user) }
            }
            .buttonStyle(DigKeyStyle(dense: true))
        }
        .padding(.horizontal, 16)
        .frame(height: 68)
        .background(Theme.bgBase)
    }

    private var folderList: some View {

        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(model.browse.folders) { folder in
                    FolderRowView(
                        folder: folder,
                        isSelected: model.browse.selectedFolder == folder.name
                    ) {
                        Task { await model.browse.loadFiles(folder: folder.name) }
                    }
                }
            }
            .padding(.vertical, 6)
        }
    }

    private var fileList: some View {

        VStack(spacing: 0) {
            HStack(spacing: 10) {
                InstrumentLabel(text: "FILE").frame(maxWidth: .infinity, alignment: .leading)
                InstrumentLabel(text: "LENGTH").frame(width: 58, alignment: .trailing)
                InstrumentLabel(text: "QUALITY").frame(width: 74, alignment: .trailing)
                InstrumentLabel(text: "SIZE").frame(width: 74, alignment: .trailing)
            }
            .padding(.horizontal, 16)
            .frame(height: 30)
            .background(Theme.bgBase)

            Divider().overlay(Theme.border)

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(model.browse.filteredFiles) { file in
                        FileRowView(
                            file: file,
                            isSelected: selectedFile == file.id,
                            isPlaying: model.player.title == file.name
                                && model.player.isPlaying
                        ) {
                            selectedFile = file.id
                        } onPlay: {
                            selectedFile = file.id
                            Task { await audition(file) }
                        }
                    }

                    if model.browse.files.count < model.browse.fileTotal {
                        Button("Load more") {
                            Task { await model.browse.loadMoreFiles() }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .padding(.vertical, 10)
                    }
                }
            }
            .focused($filesFocused)
            .onKeyPress(.return) {
                guard let selectedFile,
                      let file = model.browse.files.first(where: { $0.id == selectedFile })
                else { return .ignored }

                Task { await audition(file) }
                return .handled
            }
            .onKeyPress(.downArrow) {
                moveSelection(by: 1)
                return .handled
            }
            .onKeyPress(.upArrow) {
                moveSelection(by: -1)
                return .handled
            }
            .onAppear { filesFocused = true }
        }
    }

    private func audition(_ file: SharedFileRow) async {
        guard let user = model.browse.selectedUser,
              let folder = model.browse.selectedFolder else { return }

        await model.audition(user: user, folder: folder, file: file)
    }

    private func moveSelection(by delta: Int) {

        let files = model.browse.filteredFiles

        guard !files.isEmpty else { return }

        guard let current = selectedFile,
              let index = files.firstIndex(where: { $0.id == current }) else {
            selectedFile = files.first?.id
            return
        }

        let next = max(0, min(files.count - 1, index + delta))
        selectedFile = files[next].id
    }

    private func size(_ bytes: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: bytes, countStyle: .binary)
    }
}

struct FolderRowView: View {

    let folder: BrowserModel.FolderRow
    let isSelected: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(folder.title)
                    .font(Theme.sans(12, folder.depth > 0 ? .regular : .medium))
                    .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                    .lineLimit(1)

                Spacer(minLength: 4)

                Text("\(folder.count)")
                    .font(Theme.mono(10))
                    .foregroundStyle(Theme.textMuted)
            }
            .padding(.leading, 12 + CGFloat(min(folder.depth, 6)) * 12)
            .padding(.trailing, 12)
            .frame(height: 32)
            .background(isSelected ? Theme.bgRowSelected : (hover ? Theme.bgHover : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}

struct FileRowView: View {

    let file: SharedFileRow
    let isSelected: Bool
    let isPlaying: Bool
    let onSelect: () -> Void
    let onPlay: () -> Void

    @State private var hover = false

    var body: some View {
        HStack(spacing: 10) {
            Button(action: onPlay) {
                Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(isPlaying ? Theme.accent : Theme.textTertiary)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(hover || isSelected ? Theme.bgElevated : .clear))
            }
            .buttonStyle(.plain)
            .opacity(hover || isSelected || isPlaying ? 1 : 0.55)

            Text(file.name)
                .font(Theme.sans(13, .medium))
                .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                .lineLimit(1)

            Spacer(minLength: 6)

            Text(file.length.map { TimeFormat.clock(Double($0)) } ?? "—")
                .font(Theme.mono(11))
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 58, alignment: .trailing)

            Text(quality)
                .font(Theme.mono(10))
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 74, alignment: .trailing)

            Text(ByteCountFormatter.string(fromByteCount: file.size, countStyle: .binary))
                .font(Theme.mono(10))
                .foregroundStyle(Theme.textTertiary)
                .frame(width: 74, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .frame(height: Theme.rowHeight)
        .background(isSelected ? Theme.bgRowSelected : (hover ? Theme.bgHover : .clear))
        .contentShape(Rectangle())
        .onHover { hover = $0 }
        .onTapGesture(count: 2) { onPlay() }
        .onTapGesture { onSelect() }
    }

    private var quality: String {

        if let bitrate = file.bitrate, bitrate > 0 {
            return "\(bitrate) kbps"
        }

        if let rate = file.sampleRate, let depth = file.bitDepth {
            return "\(rate / 1000)k/\(depth)"
        }

        return "—"
    }
}
