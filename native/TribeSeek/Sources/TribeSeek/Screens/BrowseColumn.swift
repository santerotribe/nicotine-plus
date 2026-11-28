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
                    if let user = model.browse.selectedUser {
                        Task { await model.browse.browse(user: user) }
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(DigIconKeyStyle(diameter: 26))
                .amberFocus(13)
                .help("Re-browse this peer")
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
                VStack(spacing: 8) {
                    if model.browse.filter.isEmpty {
                        Text("No peers yet")
                            .font(Theme.sans(12, .medium))
                            .foregroundStyle(Theme.textSecondary)
                        Text("Type a Soulseek username below.")
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                    } else {
                        HStack(spacing: 6) {
                            LED(color: Theme.textMuted, size: 4)
                            InstrumentLabel(text: "NO PEER MATCHES")
                        }

                        Text("“\(model.browse.filter)” filters the peer list, not the network.")
                            .font(Theme.sans(11))
                            .foregroundStyle(Theme.textMuted)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16)

                        Button("Search the network") {
                            let term = model.browse.filter
                            model.search.term = term
                            model.section = .search
                            Task { await model.search.run() }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .amberFocus()
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
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
                .amberFocus()
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
}
