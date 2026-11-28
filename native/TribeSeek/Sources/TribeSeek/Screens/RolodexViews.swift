// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// The collective's card index of sellers: who we keep from, what we found
/// there, and a way back to their shelf.
struct RolodexScreen: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Theme.border)

            if model.rolodex.sources.isEmpty {
                EmptyStatePane(
                    symbol: "person.2",
                    title: "No sources yet",
                    body: model.rolodex.isLoading
                        ? "Reading the crates…"
                        : "Keep a track and the peer lands here. Star a seller to keep them even after the crate is cleared."
                )
            } else {
                ScrollView {
                    LazyVGrid(
                        columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3),
                        spacing: 10
                    ) {
                        ForEach(model.rolodex.sources) { source in
                            SourceCard(model: model, source: source)
                        }
                    }
                    .padding(14)
                }
            }
        }
        .background(Theme.bgWorkspace)
        .task { await model.rolodex.load() }
    }

    private var header: some View {

        HStack(spacing: 10) {
            InstrumentLabel(text: "SOURCES")

            Text("\(model.rolodex.sources.count)")
                .font(Theme.mono(9))
                .foregroundStyle(Theme.textMuted)

            Spacer()

            DigSearchField(placeholder: "Filter sources", text: $model.rolodex.filter)
                .frame(width: 260)

            Button {
                Task { await model.rolodex.load() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10, weight: .medium))
            }
            .buttonStyle(DigIconKeyStyle(diameter: 26))
            .amberFocus(13)
            .help("Reload the sources")
        }
        .padding(.horizontal, 14)
        .frame(height: 46)
        .background(Theme.bgBase)
    }
}

struct SourceCard: View {

    @Bindable var model: AppModel
    let source: RolodexModel.Source

    var body: some View {

        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 9) {
                Monogram(text: source.username, size: 34)

                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 5) {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 6, height: 6)
                            .overlay(Circle().strokeBorder(Theme.borderMedium, lineWidth: 0.5))
                            .help(statusLabel)

                        Text(source.username)
                            .font(Theme.sans(13, .semibold))
                            .foregroundStyle(Theme.textPrimary)
                            .lineLimit(1)
                    }

                    Text(source.lastLabel.isEmpty ? "no keeps yet" : "last kept \(source.lastLabel)")
                        .font(Theme.mono(8.5))
                        .foregroundStyle(Theme.textMuted)
                        .lineLimit(1)
                }

                Spacer(minLength: 4)

                Button {
                    model.rolodex.toggleStar(source.username)
                } label: {
                    Image(systemName: source.starred ? "star.fill" : "star")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(source.starred ? Theme.accent : Theme.textMuted)
                }
                .buttonStyle(.plain)
                .help(source.starred ? "Unstar this source" : "Star this source")
            }

            Text(source.statsLabel)
                .font(Theme.mono(8.5))
                .foregroundStyle(Theme.textTertiary)

            if let top = source.topFolderName {
                Text(top)
                    .font(Theme.sans(11))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
                    .help(source.topFolder ?? "")
            }

            if !source.foundByList.isEmpty {
                Text("found by \(source.foundByList)")
                    .font(Theme.mono(8))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
            }

            Spacer(minLength: 2)

            HStack(spacing: 6) {
                Text("\(source.folderCount) bins")
                    .font(Theme.mono(8.5))
                    .foregroundStyle(Theme.textMuted)

                Spacer()

                Button("Open shelf") {
                    Task {
                        if let folder = source.topFolder, !folder.isEmpty {
                            await model.dig(user: source.username, folder: folder)
                        } else {
                            await model.browse(user: source.username)
                        }
                    }
                }
                .buttonStyle(DigKeyStyle(dense: true))
                .amberFocus()
            }
        }
        .padding(12)
        .frame(height: 158, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Theme.bgCard)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(source.starred ? Theme.accent.opacity(0.35) : Theme.border,
                              lineWidth: 1)
        )
    }

    private var status: String {
        model.rolodex.statuses[source.username] ?? "unknown"
    }

    private var statusColor: Color {
        switch status {
        case "online": Theme.statusSaved
        case "away": Theme.accent
        case "offline": Theme.textMuted
        default: Color.clear
        }
    }

    private var statusLabel: String {
        switch status {
        case "online": "Online"
        case "away": "Away"
        case "offline": "Offline"
        default: "Status unknown"
        }
    }
}
