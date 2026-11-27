#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build and launch the native client. With no NICOTINE_API_URL the app probes
# 127.0.0.1:8766 and starts the Python engine headless if nothing answers.

set -euo pipefail

cd "$(dirname "$0")"

# The app starts the engine from the checkout when nothing answers on 8766.
export NICOTINE_REPO="${NICOTINE_REPO:-$(cd ../.. && pwd)}"
SCRATCH="${TRIBE_SCRATCH:-/tmp/tribeseek-build}"
CACHE="${TRIBE_CACHE:-/tmp/tribeseek-cache}"

swift build --disable-sandbox --scratch-path "$SCRATCH" --cache-path "$CACHE"

if [[ "${TRIBE_SELFTEST:-0}" == "1" ]]; then
  exec "$SCRATCH/debug/TribeSeek"
fi

exec "$SCRATCH/debug/TribeSeek" "$@"
