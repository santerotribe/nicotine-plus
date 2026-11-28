// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Detail for Browse: the peer's folders and files, Enter to audition.
struct BrowseDetail: View {

    @Bindable var model: AppModel

    @State private var selectedFile: String?
    @State private var showPeers = false
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

                Divider().overlay(Theme.border)

                fileList
                    .frame(width: 470)
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

                if let folder = model.browse.selectedFolder {
                    Text(folder)
                        .font(Theme.mono(9))
                        .foregroundStyle(Theme.textMuted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }

            if !model.browse.note.isEmpty {
                Text(model.browse.note)
                    .font(Theme.mono(8.5))
                    .foregroundStyle(Theme.accent)
                    .lineLimit(1)
            }

            Spacer()

            Button("Switch peer") {
                showPeers = true
            }
            .buttonStyle(DigKeyStyle(dense: true))
            .amberFocus()
            .popover(isPresented: $showPeers, arrowEdge: .bottom) {
                BrowseColumn(model: model)
                    .frame(width: 330, height: 470)
                    .onChange(of: model.browse.selectedUser) { _, _ in
                        showPeers = false
                    }
            }

            Button("Refresh") {
                Task { await model.browse.browse(user: user, force: true) }
            }
            .buttonStyle(DigKeyStyle(dense: true))
            .amberFocus()
        }
        .padding(.horizontal, 16)
        .frame(height: 76)
        .background(Theme.bgBase)
    }

    private var folderList: some View {

        VStack(spacing: 0) {
            HStack(spacing: 6) {
                DigSearchField(placeholder: "Filter folders", text: $model.browse.folderFilter)

                Button {
                    model.browse.binGrid.toggle()
                } label: {
                    Image(systemName: model.browse.binGrid ? "list.bullet" : "square.grid.2x2")
                        .font(.system(size: 10, weight: .medium))
                }
                .buttonStyle(DigIconKeyStyle(diameter: 24))
                .amberFocus(12)
                .help(model.browse.binGrid ? "List the folders" : "Show the bins")
            }
            .padding(.horizontal, 10)
            .frame(height: 34)

            HStack(spacing: 4) {
                ForEach(BrowserModel.BinSort.allCases) { sort in
                    Button(sort.title) {
                        model.browse.binSort = sort
                    }
                    .buttonStyle(ShelfChipStyle(isOn: model.browse.binSort == sort))
                    .amberFocus(3)
                }

                Spacer()
            }
            .padding(.horizontal, 10)
            .frame(height: 28)

            Divider().overlay(Theme.border)

            ScrollViewReader { proxy in
            ScrollView {
                if model.browse.binGrid, !model.browse.sortedFolders.isEmpty {
                    LazyVGrid(
                        columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3),
                        spacing: 8
                    ) {
                        ForEach(model.browse.sortedFolders) { folder in
                            BinCard(
                                folder: folder,
                                isSelected: model.browse.selectedFolder == folder.name,
                                isFresh: model.browse.fresh.contains(folder.name)
                            ) {
                                Task { await model.browse.loadFiles(folder: folder.name) }
                            }
                            .id(folder.name)
                        }
                    }
                    .padding(10)
                } else {
                    LazyVStack(spacing: 0) {
                    ForEach(model.browse.sortedFolders) { folder in
                        FolderRowView(
                            folder: folder,
                            isSelected: model.browse.selectedFolder == folder.name,
                            isFresh: model.browse.fresh.contains(folder.name)
                        ) {
                            Task { await model.browse.loadFiles(folder: folder.name) }
                        }
                        .id(folder.name)
                    }

                    if model.browse.sortedFolders.isEmpty {
                        if model.browse.isBrowsing && model.browse.folders.isEmpty {
                            HStack(spacing: 6) {
                                ProgressView().controlSize(.small)
                                InstrumentLabel(text: "WAITING FOR THE PEER", color: Theme.textMuted)
                            }
                            .padding(.vertical, 22)

                        } else if !model.browse.folderFilter.isEmpty {
                            Text("No folder in this share matches “\(model.browse.folderFilter)”.")
                                .font(Theme.sans(11))
                                .foregroundStyle(Theme.textMuted)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 20)
                        }
                    }
                }
                    .padding(.vertical, 4)
                }
            }
            .task(id: model.browse.selectedFolder) {
                guard model.browse.scrollToSelection,
                      let folder = model.browse.selectedFolder else { return }

                try? await Task.sleep(nanoseconds: 60_000_000)

                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo(folder, anchor: .center)
                }

                model.browse.scrollToSelection = false
            }
            }
        }
    }

    @ViewBuilder
    private var inspectorHeader: some View {

        if let name = model.browse.selectedFolder,
           let folder = model.browse.folders.first(where: { $0.name == name }) {

            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(folder.title)
                        .font(Theme.sans(13, .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(2)

                    if folder.isGeneric, !folder.collectionTitle.isEmpty {
                        Text(folder.collectionTitle)
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }

                    HStack(spacing: 10) {
                        InstrumentLabel(text: "\(folder.count) FILES")
                        InstrumentLabel(text: folder.sizeLabel)

                        if !folder.qualityLabel.isEmpty {
                            InstrumentLabel(text: folder.qualityLabel)
                        }
                    }
                }

                Spacer(minLength: 8)

                if let user = model.browse.selectedUser, let file = firstPlayableFile {
                    VStack(alignment: .trailing, spacing: 6) {
                        Button("Audition bin") {
                            Task {
                                await model.audition(user: user, folder: name, file: file)
                            }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .amberFocus()
                        .help("Audition the first track in this bin")

                        Button("Keep all") {
                            Task {
                                await model.keepBin(user: user, folder: name)
                            }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .amberFocus()
                        .help("Keep every audio file in this bin for the Sample crate")
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.bgBase)
            .overlay(alignment: .bottom) {
                Rectangle().fill(Theme.border).frame(height: 1)
            }
        }
    }

    private var playableFiles: [SharedFileRow] {

        let extensions: Set<String> = ["mp3", "flac", "wav", "aif", "aiff", "m4a", "ogg", "opus"]

        return model.browse.files.filter {
            extensions.contains(($0.name as NSString).pathExtension.lowercased())
        }
    }

    private var firstPlayableFile: SharedFileRow? {
        playableFiles.first
    }

    private var fileList: some View {

        VStack(spacing: 0) {
            inspectorHeader

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

            ScrollViewReader { proxy in
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
                            .id(file.id)
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
                .onChange(of: selectedFile) { _, newValue in
                    guard let newValue else { return }

                    withAnimation(.easeOut(duration: 0.12)) {
                        proxy.scrollTo(newValue, anchor: .center)
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
    let isFresh: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(folder.title)
                            .font(Theme.sans(12.5, .medium))
                            .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.middle)

                        if isFresh {
                            LED(color: Theme.accent, size: 4)
                        }
                    }

                    Text(subtitle)
                        .font(Theme.mono(8.5))
                        .foregroundStyle(Theme.textMuted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer(minLength: 4)

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(folder.count)")
                        .font(Theme.mono(11))
                        .foregroundStyle(isSelected ? Theme.accent : Theme.textMuted)
                        .monospacedDigit()

                    Text(folder.sizeLabel)
                        .font(Theme.mono(8))
                        .foregroundStyle(Theme.textMuted)
                }
            }
            .padding(.leading, 12 + CGFloat(min(folder.depth, 3)) * 8)
            .padding(.trailing, 12)
            .frame(height: 48)
            .background {
                if isSelected {
                    WellSurface(radius: 0, tint: Theme.accent.opacity(0.05))
                } else if hover {
                    Color.white.opacity(0.03)
                }
            }
            .overlay(alignment: .leading) {
                if isSelected {
                    Rectangle().fill(Theme.accent).frame(width: 2)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }

    private var parent: String {

        var parts = folder.name.split(separator: "\\").map(String.init)

        guard parts.count > 1 else { return "" }

        parts.removeLast()

        return parts.joined(separator: "\\")
    }

    private var subtitle: String {
        [parent, folder.qualityLabel]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
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
                    .foregroundStyle(isPlaying ? Material.litInk : Theme.textTertiary)
                    .frame(width: 22, height: 22)
                    .background {
                        if isPlaying {
                            Circle().fill(
                                LinearGradient(colors: [Material.litCore, Material.litMid],
                                               startPoint: .top, endPoint: .bottom)
                            )
                        } else if hover || isSelected {
                            Circle().fill(Theme.bgElevated)
                        }
                    }
                    .overlay {
                        if isPlaying {
                            Circle().strokeBorder(Color.black.opacity(0.35), lineWidth: 1)
                        }
                    }
            }
            .buttonStyle(.plain)
            .opacity(hover || isSelected || isPlaying ? 1 : 0.55)
            .help("Audition")

            Text(file.name)
                .font(Theme.sans(13, .medium))
                .foregroundStyle(isPlaying ? Theme.accent : (isSelected ? Theme.textPrimary : Theme.textSecondary))
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
        .background {
            if isSelected {
                WellSurface(radius: 0, tint: Theme.accent.opacity(0.05))
            } else if hover {
                Color.white.opacity(0.045)
            }
        }
        .overlay(alignment: .leading) {
            if isSelected {
                Rectangle().fill(Theme.accent).frame(width: 2)
            }
        }
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


struct BinCard: View {

    let folder: BrowserModel.FolderRow
    let isSelected: Bool
    let isFresh: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 3) {
                if folder.isGeneric, !folder.collectionTitle.isEmpty {
                    Text(folder.collectionTitle.uppercased())
                        .font(Theme.mono(7))
                        .tracking(0.9)
                        .foregroundStyle(Theme.textMuted)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                HStack(alignment: .top, spacing: 4) {
                    Text(folder.title)
                        .font(Theme.sans(11.5, .medium))
                        .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    if isFresh {
                        LED(color: Theme.accent, size: 4)
                            .padding(.top, 3)
                    }
                }

                Text(folder.qualityLabel)
                    .font(Theme.mono(7.5))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)

                Spacer(minLength: 2)

                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text("\(folder.count)")
                        .font(Theme.mono(15))
                        .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
                        .monospacedDigit()

                    InstrumentLabel(text: "files", color: Theme.textMuted, tracking: 0.8)

                    Spacer(minLength: 2)

                    Text(folder.sizeLabel)
                        .font(Theme.mono(8))
                        .foregroundStyle(Theme.textMuted)
                }
            }
            .padding(9)
            .frame(height: 104)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isSelected ? Theme.accent.opacity(0.06)
                          : (hover ? Theme.bgHover : Theme.bgControl))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .strokeBorder(isSelected ? Theme.accent.opacity(0.55) : Theme.border,
                                  lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}



struct ShelfChipStyle: ButtonStyle {

    let isOn: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.mono(8))
            .tracking(0.8)
            .foregroundStyle(isOn ? Theme.accent : Theme.textMuted)
            .padding(.horizontal, 7)
            .frame(height: 20)
            .background(
                RoundedRectangle(cornerRadius: 3)
                    .fill(isOn ? Theme.accent.opacity(0.06) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 3)
                    .strokeBorder(isOn ? Theme.accent.opacity(0.45) : Theme.border,
                                  lineWidth: 1)
            )
            .contentShape(Rectangle())
    }
}

