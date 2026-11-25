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

                HStack(spacing: 0) {
                    Group {
                        switch model.section {
                        case .browse:
                            BrowseColumn(model: model)
                        case .search:
                            SearchColumn(model: model)
                        case .audition:
                            AuditionColumn(model: model)
                        case .crate:
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
                        case .browse:
                            BrowseDetail(model: model)
                        case .search:
                            SearchDetail(model: model)
                        case .crate:
                            CrateDetail(model: model)
                        case .audition:
                            AuditionPane(model: model, compact: false)
                        default:
                            EmptyStatePane(
                                symbol: model.section.symbol,
                                title: model.section.title,
                                body: "The engine already serves this. The shell for it lands next."
                            )
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }

                Divider().overlay(Theme.border)
                Transport(model: model)
            }
        }
        .background(Theme.bgCanvas)
        .ignoresSafeArea(.container, edges: .top)
        .task(id: model.section) { await model.activateSection() }
    }
}

// MARK: - Rail

struct Rail: View {

    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            ForEach(AppModel.Section.allCases) { section in
                if section == .audition || section == .crate || section == .settings {
                    RailSeparator()
                }

                RailItem(section: section, isSelected: model.section == section) {
                    model.section = section
                }
            }

            Spacer(minLength: 8)

            account

            Button {
                model.section = .settings
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 13, weight: .medium))
            }
            .buttonStyle(DigIconKeyStyle(diameter: 32))
            .padding(.bottom, 14)
            .help("Settings")
        }
        .frame(width: Theme.railWidth)
        .background(Material.chrome)
        .overlay(alignment: .top) { PanelRim() }
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
        .onHover { hover = $0 }
        .animation(.easeInOut(duration: 0.12), value: hover)
    }
}

// MARK: - Top strip

struct TopStrip: View {

    @Bindable var model: AppModel

    var body: some View {
        ZStack {
            Text(model.section.title)
                .font(Theme.sans(13, .semibold))
                .tracking(0.3)
                .foregroundStyle(Theme.textPrimary)
                .shadow(color: .black.opacity(0.5), radius: 0, y: 0.5)

            HStack {
                HStack(spacing: 6) {
                    LED(isOn: model.isConnected,
                        color: model.isConnected ? Theme.statusSaved : Theme.statusError,
                        size: 5)

                    InstrumentLabel(
                        text: model.isConnected
                            ? (model.state?.username ?? "CONNECTED")
                            : (model.supervisor.message),
                        color: Theme.textMuted
                    )
                }
                .padding(.leading, 12)

                Spacer()

                HStack(spacing: 6) {
                    iconKey("arrow.left.arrow.right", help: "Transfers")
                    iconKey("bell", help: "Activity")
                    iconKey("gearshape", help: "Settings")
                }
            }
            .padding(.trailing, 12)
        }
        .frame(height: Theme.topStripHeight)
        .background(Material.chrome)
        .overlay(alignment: .top) { PanelRim() }
    }

    private func iconKey(_ symbol: String, help: String) -> some View {
        Button {
        } label: {
            Image(systemName: symbol)
        }
        .buttonStyle(DigIconKeyStyle(diameter: 26))
        .help(help)
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
                Image(systemName: symbol)
                    .font(.system(size: 30, weight: .light))
                    .foregroundStyle(Theme.textSecondary)

                Text(title)
                    .font(Theme.sans(20, .semibold))
                    .foregroundStyle(Theme.textPrimary)

                Text(message)
                    .font(Theme.sans(12))
                    .foregroundStyle(Theme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(24)
            .frame(maxWidth: 420, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: Theme.radiusPanel).fill(Theme.bgCard))
            .overlay(RoundedRectangle(cornerRadius: Theme.radiusPanel)
                .strokeBorder(Theme.border, lineWidth: 1))
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
