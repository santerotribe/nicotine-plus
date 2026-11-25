// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

struct SearchColumn: View {

    @Bindable var model: AppModel
    @FocusState private var fieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                DigSearchField(
                    placeholder: "Search Soulseek",
                    text: $model.search.term,
                    onSubmit: { Task { await model.search.run() } },
                    focus: $fieldFocused
                )

                Button("Go") {
                    Task { await model.search.run() }
                }
                .buttonStyle(DigKeyStyle(dense: true))
                .amberFocus()
                .disabled(model.search.isSearching || model.search.term.isEmpty)
            }
            .padding(.horizontal, 12)
            .frame(height: 44)
            .onAppear { fieldFocused = true }

            Divider().overlay(Theme.border)

            if model.search.results.isEmpty {
                VStack(spacing: 8) {
                    if !model.search.error.isEmpty {
                        HStack(spacing: 6) {
                            LED(isOn: true, color: Theme.statusError, size: 4)
                            InstrumentLabel(text: "NOTHING CAME BACK", color: Theme.statusError)
                        }

                        Text(model.search.error)
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16)
                    } else if model.search.isSearching {
                        HStack(spacing: 6) {
                            LED(color: Theme.accent, size: 4)
                            InstrumentLabel(text: "SEARCHING…", color: Theme.accent)
                        }

                        Text("Results stream in as peers answer.")
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                    } else {
                        InstrumentLabel(text: "NO SEARCH YET")
                        Text("Type a term and press Return.")
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
            }

            ScrollView {
                LazyVStack(spacing: 0, pinnedViews: [.sectionHeaders]) {
                    ForEach(model.search.groups) { group in
                        Section {
                            ForEach(group.results) { result in
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
                        } header: {
                            SearchGroupHeader(name: group.username, count: group.results.count)
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
                    LED(color: Theme.accent, size: 4)
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

/// A peer band that stays pinned while its results scroll: engraved name, count
/// on the right, one line under it.
struct SearchGroupHeader: View {

    let name: String
    let count: Int

    var body: some View {
        HStack(spacing: 8) {
            LED(color: Theme.accent, size: 4)

            Text(name)
                .font(Theme.sans(11, .semibold))
                .tracking(0.1)
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)

            Spacer()

            Text("\(count)")
                .font(Theme.monoStrong(10))
                .foregroundStyle(Theme.textTertiary)
        }
        .padding(.horizontal, 12)
        .frame(height: 28)
        .background(Material.chrome)
        .overlay(alignment: .bottom) { Rectangle().fill(Color.black.opacity(0.5)).frame(height: 1) }
        .overlay(alignment: .top) { PanelRim() }
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
                    .amberFocus()

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
                body: "Type a term and press Return. Peers are grouped as results arrive; pick a row to audition it."
            )
        }
    }
}
