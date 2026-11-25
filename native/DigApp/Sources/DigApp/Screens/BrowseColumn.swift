// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Middle column for Browse: the peers you have opened, plus a way to open one.
struct BrowseColumn: View {

    @Bindable var model: AppModel
    @State private var newUser = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                DigSearchField(placeholder: "Filter peers", text: $model.browse.filter)

                Button {
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .help("Refresh")
            }
            .padding(.horizontal, 12)
            .frame(height: 44)

            Divider().overlay(Theme.border)

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(filteredUsers, id: \.self) { username in
                        PeerRow(
                            username: username,
                            isSelected: model.browse.selectedUser == username,
                            isLoading: model.browse.isBrowsing && model.browse.selectedUser == username
                        ) {
                            Task { await model.browse.select(user: username) }
                        }
                    }
                }
            }

            if filteredUsers.isEmpty {
                VStack(spacing: 6) {
                    Text("No peers yet")
                        .font(Theme.sans(12, .medium))
                        .foregroundStyle(Theme.textSecondary)
                    Text("Type a Soulseek username below.")
                        .font(Theme.sans(11))
                        .foregroundStyle(Theme.textMuted)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 28)
            }

            Divider().overlay(Theme.border)

            HStack(spacing: 8) {
                DigSearchField(placeholder: "Open a peer…", text: $newUser)

                Button("Browse") {
                    let name = newUser.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !name.isEmpty else { return }
                    newUser = ""
                    Task { await model.browse(user: name) }
                }
                .buttonStyle(DigKeyStyle(dense: true))
                .disabled(newUser.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 12)
            .frame(height: 48)
            .background(Theme.bgBase)

            if !model.browse.error.isEmpty {
                Text(model.browse.error)
                    .font(Theme.sans(11))
                    .foregroundStyle(Theme.statusError)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Theme.bgCanvas)
    }

    private var filteredUsers: [String] {

        let filter = model.browse.filter

        guard !filter.isEmpty else { return model.browse.users }
        return model.browse.users.filter { $0.localizedCaseInsensitiveContains(filter) }
    }
}

struct PeerRow: View {

    let username: String
    let isSelected: Bool
    let isLoading: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Monogram(text: username, size: 40)

                VStack(alignment: .leading, spacing: 3) {
                    Text(username)
                        .font(Theme.sans(13, .medium))
                        .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                        .lineLimit(1)

                    if isLoading {
                        Text("browsing…")
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                    }
                }

                Spacer()

                if isSelected {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Theme.textMuted)
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 56)
            .background(isSelected ? Theme.bgRowSelected : (hover ? Theme.bgHover : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}
