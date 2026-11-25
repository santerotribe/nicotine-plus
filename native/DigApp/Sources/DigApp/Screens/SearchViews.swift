// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

struct SearchColumn: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                DigSearchField(placeholder: "Search Soulseek", text: $model.search.term)

                Button("Go") {
                    Task { await model.search.run() }
                }
                .buttonStyle(DigKeyStyle(dense: true))
                .disabled(model.search.isSearching || model.search.term.isEmpty)
            }
            .padding(.horizontal, 12)
            .frame(height: 44)

            Divider().overlay(Theme.border)

            if model.search.term.isEmpty && model.search.results.isEmpty {
                VStack(spacing: 6) {
                    InstrumentLabel(text: "NO SEARCH YET")
                    Text("Results stream in while the network answers.")
                        .font(Theme.sans(11))
                        .foregroundStyle(Theme.textMuted)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
            }

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(model.search.results) { result in
                        SearchResultRowView(
                            result: result,
                            isSelected: model.search.selectedID == result.id
                        ) {
                            model.search.selectedID = result.id
                        } onPlay: {
                            model.search.selectedID = result.id
                            Task {
                                await model.audition(user: result.username,
                                                      folder: result.folder,
                                                      file: result.asFile)
                            }
                        }
                    }

                    if model.search.results.count < model.search.total {
                        Button("Load more") {
                            Task { await model.search.loadMore() }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .padding(.vertical, 10)
                    }
                }
            }

            HStack {
                InstrumentLabel(text: "\(model.search.results.count) OF \(model.search.total) RESULTS",
                                color: Theme.textMuted)
                Spacer()
                if model.search.isSearching {
                    InstrumentLabel(text: "SEARCHING…")
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(Theme.bgBase)

            if !model.search.error.isEmpty {
                Text(model.search.error)
                    .font(Theme.sans(11))
                    .foregroundStyle(Theme.statusError)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Theme.bgCanvas)
    }
}

struct SearchResultRowView: View {

    let result: SearchResultRow
    let isSelected: Bool
    let onSelect: () -> Void
    let onPlay: () -> Void

    @State private var hover = false

    var body: some View {
        HStack(spacing: 10) {
            Button(action: onPlay) {
                Image(systemName: "play.fill")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(hover || isSelected ? Theme.bgElevated : .clear))
            }
            .buttonStyle(.plain)
            .opacity(hover || isSelected ? 1 : 0.5)

            VStack(alignment: .leading, spacing: 3) {
                Text(result.filename)
                    .font(Theme.sans(12, .medium))
                    .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                    .lineLimit(1)

                Text(result.username + (result.folder.isEmpty ? "" : " · " + result.folder))
                    .font(Theme.sans(10))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
            }

            Spacer(minLength: 6)

            Text(result.length.map { TimeFormat.clock(Double($0)) } ?? "—")
                .font(Theme.mono(10))
                .foregroundStyle(Theme.textTertiary)

            if !result.slotAvailable {
                InstrumentLabel(text: "#\(result.queuePosition)", color: Theme.textMuted)
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 52)
        .background(isSelected ? Theme.bgRowSelected : (hover ? Theme.bgHover : .clear))
        .contentShape(Rectangle())
        .onHover { hover = $0 }
        .onTapGesture(count: 2) { onPlay() }
        .onTapGesture { onSelect() }
    }
}

struct SearchDetail: View {

    @Bindable var model: AppModel

    var body: some View {
        if let result = model.search.selected {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(result.filename)
                        .font(Theme.sans(18, .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        InstrumentLabel(text: result.username)
                        InstrumentLabel(text: result.bitrate.map { "\($0) KBPS" } ?? "LOSSLESS")
                        Text(ByteCountFormatter.string(fromByteCount: result.size, countStyle: .binary))
                            .font(Theme.mono(10))
                            .foregroundStyle(Theme.textTertiary)
                    }
                }

                Text(result.folder)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    Button {
                        Task {
                            await model.audition(user: result.username,
                                                 folder: result.folder,
                                                 file: result.asFile)
                        }
                    } label: {
                        Label("Audition", systemImage: "play.fill")
                    }
                    .buttonStyle(DigPrimaryKeyStyle())

                    InstrumentLabel(
                        text: result.slotAvailable ? "SLOT FREE" : "QUEUE #\(result.queuePosition)",
                        color: result.slotAvailable ? Theme.statusSaved : Theme.textTertiary
                    )
                }

                Spacer()
            }
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Theme.bgWorkspace)

        } else {
            EmptyStatePane(
                symbol: "magnifyingglass",
                title: "Search the network",
                body: "Type a term and press Go. Results are grouped by what the engine stores, paged as they arrive, and auditions start from the row."
            )
        }
    }
}
