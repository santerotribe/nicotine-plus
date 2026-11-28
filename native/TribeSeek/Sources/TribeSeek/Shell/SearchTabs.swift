// SPDX-FileCopyrightText: 2026 Schema Apps
// SPDX-License-Identifier: GPL-3.0-or-later

import SwiftUI

/// The search strip: one tab per query, each holding its own results. A tab is
/// a SearchModel; the engine holds the result store, the tab holds a window of
/// it, and closing the tab frees both.
struct SearchTabStrip: View {

    @Bindable var model: AppModel
    @FocusState.Binding var focus: Bool

    var body: some View {
        HStack(spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(model.searchTabs) { tab in
                        SearchTabButton(
                            tab: tab,
                            isActive: tab === model.search,
                            onSelect: { model.activate(tab) },
                            onClose: { Task { await model.closeSearch(tab) } }
                        )
                    }

                    Button {
                        model.newBlankSearch()
                        focus = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .buttonStyle(DigIconKeyStyle(diameter: 22))
                    .amberFocus(11)
                    .help("New search")
                }
                .padding(.horizontal, 8)
            }
        }
        .frame(maxHeight: .infinity)
    }
}

struct SearchTabButton: View {

    let tab: SearchModel
    let isActive: Bool
    let onSelect: () -> Void
    let onClose: () -> Void

    @State private var hover = false

    var body: some View {
        HStack(spacing: 6) {
            if tab.isSearching {
                ProgressView()
                    .controlSize(.mini)
                    .scaleEffect(0.55)
                    .frame(width: 9)
            } else if tab.isLive {
                LED(color: Theme.accent, size: 4)
            }

            Text(tab.title)
                .font(Theme.sans(11, .medium))
                .foregroundStyle(isActive ? Theme.textPrimary : Theme.textSecondary)
                .lineLimit(1)

            if tab.results.count > 0 {
                Text(tab.totalLabel)
                    .font(Theme.mono(9))
                    .foregroundStyle(Theme.textTertiary)
                    .monospacedDigit()
            }

            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(Theme.textTertiary)
                    .frame(width: 12, height: 12)
            }
            .buttonStyle(.plain)
            .opacity(hover || isActive ? 1 : 0)
            .help("Close this search")
        }
        .padding(.horizontal, 9)
        .frame(height: 22)
        .frame(maxWidth: 200)
        .background {
            if isActive {
                CapSurface(radius: 5)
            } else if hover {
                RoundedRectangle(cornerRadius: 5).fill(Theme.bgHover)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: onSelect)
        .onHover { hover = $0 }
    }
}
