# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Identify a Soulseek file against a public catalogue.

Soulseek filenames are messy ("01 Ruggier - Long Ride (Original Mix).aiff",
"04 - Some Edit [320]"), and the peer may be queued or offline. Matching the
track against the iTunes catalogue gives us an official 30 s preview we can
stream instantly -- no peer, no queue -- and a duration to sanity-check the
match before the user trusts it.

When the catalogue has nothing, callers fall back to a partial peer transfer.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from dataclasses import dataclass

ITUNES_SEARCH = "https://itunes.apple.com/search"
DEFAULT_TIMEOUT = 8.0

LEADING_TRACK_NUMBER = re.compile(
    r"^\s*(?:(?:track|tr|disc|cd)\s*\d{1,3}[\s._-]*|(?:\d{1,3}[\s._-]+)+)",
    re.IGNORECASE,
)
BRACKETED = re.compile(r"[\[(][^\])]*[\])]")
NOISE_WORDS = {
    "official", "video", "audio", "lyrics", "lyric", "hd", "hq", "explicit",
    "remaster", "remastered", "radio", "edit", "version", "mix", "original",
    "extended", "club", "dub", "instrumental", "vinyl", "rip", "web", "flac",
    "mp3", "320", "128", "256", "lossless", "promo", "bootleg",
}
SEPARATORS = re.compile(r"\s+[-–—]\s+|\s+–\s+")


@dataclass
class Candidate:
    artist: str
    title: str
    album: str
    duration: float          # seconds
    preview_url: str
    artwork: str
    store_url: str
    score: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}"


@dataclass
class ParsedName:
    artist: str
    title: str
    raw: str


def parse_filename(filename: str) -> ParsedName:
    """Split a Soulseek filename into an artist and a title guess."""

    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename.strip())
    stem = stem.replace("_", " ").strip()
    stem = BRACKETED.sub(" ", stem)
    stem = LEADING_TRACK_NUMBER.sub("", stem)
    stem = re.sub(r"\s{2,}", " ", stem).strip()
    parts = SEPARATORS.split(stem, maxsplit=1)

    if len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist, title = "", stem

    return ParsedName(artist=_tidy(artist), title=_tidy(title) or _tidy(stem), raw=filename)


def _tidy(value: str) -> str:
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" .-_")


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token and token not in NOISE_WORDS]


def similarity(left: str, right: str) -> float:
    """Token-set overlap, insensitive to punctuation and parenthetical noise."""

    a = set(_tokens(left))
    b = set(_tokens(right))

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def _request_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "nicotine-digging/1.0"})

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_itunes(term: str, limit: int = 8, timeout: float = DEFAULT_TIMEOUT) -> list[Candidate]:
    """Search the iTunes catalogue (no API key, 30 s previews)."""

    query = urllib.parse.urlencode({"term": term, "entity": "song", "limit": limit, "media": "music"})

    try:
        payload = _request_json(f"{ITUNES_SEARCH}?{query}", timeout=timeout)

    except (OSError, ValueError):
        return []

    candidates: list[Candidate] = []

    for entry in payload.get("results", []) or []:
        preview = entry.get("previewUrl") or ""

        if not preview:
            continue

        candidates.append(Candidate(
            artist=str(entry.get("artistName") or ""),
            title=str(entry.get("trackName") or ""),
            album=str(entry.get("collectionName") or ""),
            duration=float(entry.get("trackTimeMillis") or 0) / 1000.0,
            preview_url=preview,
            artwork=str(entry.get("artworkUrl100") or ""),
            store_url=str(entry.get("trackViewUrl") or ""),
        ))

    return candidates


def score_candidate(candidate: Candidate, parsed: ParsedName,
                    expected_duration: float = 0.0) -> float:
    """Blend artist/title similarity with a duration check."""

    title_score = similarity(parsed.title, candidate.title)
    artist_score = similarity(parsed.artist, candidate.artist) if parsed.artist else 0.5
    score = (title_score * 0.7) + (artist_score * 0.3)

    if expected_duration and candidate.duration:
        delta = abs(candidate.duration - expected_duration)
        # Full-length Soulseek files vs catalogue runtime: allow edits/mixes
        if delta <= 3:
            score += 0.15
        elif delta <= 15:
            score += 0.05
        elif delta > 90:
            score -= 0.2

    return max(0.0, min(1.0, score))


def resolve(filename: str, expected_duration: float = 0.0,
            minimum_score: float = 0.45, limit: int = 8) -> list[Candidate]:
    """Return catalogue matches for a filename, best first."""

    parsed = parse_filename(filename)
    queries = []

    if parsed.artist:
        queries.append(f"{parsed.artist} {parsed.title}")

    queries.append(parsed.title)

    if parsed.artist:
        queries.append(parsed.artist)

    seen: dict[str, Candidate] = {}

    for query in queries:
        for candidate in search_itunes(query, limit=limit):
            key = f"{candidate.artist}|{candidate.title}".lower()

            if key in seen:
                continue

            candidate.score = score_candidate(candidate, parsed, expected_duration)
            seen[key] = candidate

        if seen and max(item.score for item in seen.values()) >= 0.8:
            break

    ranked = sorted(seen.values(), key=lambda item: item.score, reverse=True)
    return [candidate for candidate in ranked if candidate.score >= minimum_score]


def lookup_preview(filename: str, expected_duration: float = 0.0) -> Candidate | None:
    matches = resolve(filename, expected_duration=expected_duration)
    return matches[0] if matches else None
