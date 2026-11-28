// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// Rail → list → detail, with the instrument transport pinned across the bottom.
struct AppShell: View {

    @Bindable var model: AppModel

    var body: some View {
        HStack(spacing: 0) {
            Rail(model: model)
            Divider().overlay(Theme.border)

            VStack(spacing: 0) {
                TopStrip(model: model)
                Divider().overlay(Theme.border)

                if model.section == .search {
                    SearchWorkspace(model: model)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if model.section == .shelf {
                    BrowseDetail(model: model)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                HStack(spacing: 0) {
                    Group {
                        switch model.section {
                        case .crates:
                            CrateColumn(model: model)
                        default:
                            PlaceholderColumn(title: model.section.title,
                                              body: "This section arrives with the full native shell.")
                        }
                    }
                    .frame(width: Theme.listWidth)

                    Divider().overlay(Theme.border)

                    Group {
                        switch model.section {
                        case .crates:
                            CrateDetail(model: model)
                        default:
                            EmptyStatePane(
                                symbol: model.section.symbol,
                                title: model.section.title,
                                body: "The engine already serves this. The shell for it lands next."
                            )
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    // The content sits in a case: a shadow gathers where it
                    // meets the bezel on the top and left edges.
                    .overlay(alignment: .top) {
                        LinearGradient(colors: [Color.black.opacity(0.30), .clear],
                                       startPoint: .top, endPoint: .bottom)
                            .frame(height: 12)
                            .allowsHitTesting(false)
                    }
                    .overlay(alignment: .leading) {
                        LinearGradient(colors: [Color.black.opacity(0.22), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: 10)
                            .allowsHitTesting(false)
                    }
                }
                }

                Divider().overlay(Theme.border)
                AuditionDeck(model: model)
            }
        }
        .background(Theme.bgCanvas)
        .ignoresSafeArea(.container, edges: .top)
        .background(WindowConfigurator())
        .animation(.easeInOut(duration: 0.18), value: model.trayExpanded)
        .task(id: model.section) { await model.activateSection() }
        .onChange(of: model.section) { previous, current in
            if previous == .shelf, current != .shelf {
                model.browse.commitSeen()
            }
        }
    }
}

// MARK: - Rail

struct Rail: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            ForEach(AppModel.Section.allCases) { section in
                if section == .crates || section == .rig {
                    RailSeparator()
                }

                RailItem(section: section, isSelected: model.section == section) {
                    model.section = section
                }
            }

            Spacer(minLength: 8)

            account
                .padding(.bottom, 6)
        }
        .frame(width: Theme.railWidth)
        // Clear the traffic lights: the window is full-bleed, so the rail owns
        // the titlebar zone and its first item starts below the buttons.
        .padding(.top, 30)
        .background(Material.chrome)
        .overlay(alignment: .top) { PanelRim() }
        .ignoresSafeArea(.container, edges: .bottom)
    }

    private var account: some View {

        VStack(spacing: 4) {
            Monogram(text: model.state?.username ?? "?", size: 36)

            Text(model.state.map { "\($0.privilegesDays)d" } ?? "—")
                .font(Theme.mono(9))
                .foregroundStyle(Theme.textTertiary)
        }
        .padding(.bottom, 12)
    }
}

/// A section line, the way a hardware panel divides its groups.
struct RailSeparator: View {

    var body: some View {
        Rectangle()
            .fill(
                LinearGradient(
                    colors: [.clear, Color.black.opacity(0.5), .white.opacity(0.04), .clear],
                    startPoint: .leading, endPoint: .trailing
                )
            )
            .frame(height: 1)
            .padding(.horizontal, 20)
            .padding(.vertical, 4)
    }
}

struct RailItem: View {

    let section: AppModel.Section
    let isSelected: Bool
    let action: () -> Void

    @State private var hover = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: section.symbol)
                    .font(.system(size: 17, weight: .regular))
                    .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)

                Text(section.title)
                    .font(Theme.sans(10, .medium))
                    .tracking(0.2)
                    .foregroundStyle(isSelected ? Theme.textPrimary : Theme.textSecondary)
                    .shadow(color: .black.opacity(0.5), radius: 0, y: 0.5)
            }
            .frame(width: 72, height: Theme.railItemHeight)
            .background {
                if isSelected {
                    CapSurface(radius: Theme.radiusPanel)
                } else if hover {
                    RoundedRectangle(cornerRadius: Theme.radiusPanel).fill(Theme.bgHover)
                }
            }
            .overlay(alignment: .topTrailing) {
                if isSelected {
                    LED(color: Theme.accent, size: 4)
                        .padding(.top, 7)
                        .padding(.trailing, 10)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .amberFocus(Theme.radiusPanel)
        .onHover { hover = $0 }
        .animation(.easeInOut(duration: 0.12), value: hover)
    }
}

// MARK: - Top strip

struct TopStrip: View {

    @Bindable var model: AppModel
    @FocusState private var searchFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                HStack(spacing: 8) {
                    LED(isOn: connectionLED.isOn, color: connectionLED.color, size: 5)

                    InstrumentLabel(text: connectionLabel, color: Theme.textMuted)
                        .lineLimit(1)

                    if !model.isOnline && model.isConnected {
                        Button("Reconnect") {
                            Task { await model.reconnect() }
                        }
                        .buttonStyle(DigKeyStyle(dense: true))
                        .amberFocus()
                    }
                }
                .padding(.leading, 12)

                Spacer(minLength: 16)

                DigSearchField(
                    placeholder: "Search Soulseek — Return opens a tab",
                    text: $model.searchDraft,
                    onSubmit: { Task { await model.submitSearch() } },
                    focus: $searchFocused
                )
                .frame(width: 320)

                Button("Go") {
                    Task { await model.submitSearch() }
                }
                .buttonStyle(DigKeyStyle(dense: true))
                .amberFocus()
                .disabled(model.searchDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                .padding(.trailing, 12)
            }
            .frame(height: 34)

            Divider().overlay(Theme.border)

            SearchTabStrip(model: model, focus: $searchFocused)
                .frame(height: 30)
        }
        .frame(height: Theme.topStripHeight)
        .background(Material.chrome)
        .overlay(alignment: .top) { PanelRim() }
    }

    /// Green when the Soulseek connection is up, amber while it retries, red
    /// when the account is offline — the engine can be reachable and logged out.
    private var connectionLED: (isOn: Bool, color: Color) {
        switch model.state?.connection {
        case .online:
            return (true, Theme.statusSaved)
        case .connecting:
            return (true, Theme.accent)
        default:
            return (model.isConnected, Theme.statusError)
        }
    }

    private var connectionLabel: String {
        switch model.state?.connection {
        case .online:
            return model.state?.username ?? "ONLINE"
        case .connecting:
            return "CONNECTING"
        default:
            guard model.isConnected else { return model.supervisor.message }

            return model.accountInUse ? "ACCOUNT IN USE ELSEWHERE" : "SOULSEEK OFFLINE"
        }
    }

}

// MARK: - Shared empty state

struct EmptyStatePane: View {

    let symbol: String
    let title: String
    let message: String

    init(symbol: String, title: String, body: String) {
        self.symbol = symbol
        self.title = title
        self.message = body
    }

    var body: some View {
        VStack {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 6) {
                    LED(color: Theme.accent, size: 4)
                    InstrumentLabel(text: "IDLE", color: Theme.textMuted)
                }

                Image(systemName: symbol)
                    .font(.system(size: 30, weight: .light))
                    .foregroundStyle(Theme.textSecondary)

                Text(title)
                    .font(Theme.sans(19, .semibold))
                    .tracking(-0.1)
                    .foregroundStyle(Theme.textPrimary)

                Text(message)
                    .font(Theme.sans(12))
                    .foregroundStyle(Theme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(24)
            .frame(maxWidth: 440, alignment: .leading)
            .background(WellSurface(radius: Theme.radiusPanel))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bgWorkspace)
    }
}

struct PlaceholderColumn: View {

    let title: String
    let message: String

    init(title: String, body: String) {
        self.title = title
        self.message = body
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(Theme.sans(13, .semibold))
                .foregroundStyle(Theme.textPrimary)

            Text(message)
                .font(Theme.sans(11))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)

            Spacer()
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.bgCanvas)
    }
}
