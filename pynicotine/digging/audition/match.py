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
from functools import lru_cache

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
SEPARATORS = re.compile(r"\s*[-–—]\s+|\s+[-–—]\s*")


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
    source: str = "itunes"   # itunes | youtube
    stream_url: str = ""     # resolved on demand for youtube

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


def _fold(value: str) -> str:
    """Lowercase and strip accents so 'Chloé' matches 'Chloe'."""

    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", _fold(value)) if token and token not in NOISE_WORDS]


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


@lru_cache(maxsize=256)
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


def _clean_uploader(uploader: str) -> str:
    """'Ruggier - Topic' / 'ArtistVEVO' -> 'Ruggier' / 'Artist'."""

    value = re.sub(r"\s*-\s*Topic\s*$", "", uploader or "", flags=re.IGNORECASE)
    value = re.sub(r"VEVO$", "", value, flags=re.IGNORECASE)
    return value.strip()


@lru_cache(maxsize=256)
def search_youtube(term: str, limit: int = 8, timeout: float = 15.0) -> list[Candidate]:
    """Search YouTube through yt-dlp without downloading anything."""

    try:
        import yt_dlp

    except ImportError:
        return []

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noprogress": True,
        "socket_timeout": timeout,
        "playlist_items": f"1-{max(1, limit)}",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{max(1, limit)}:{term}", download=False)

    except Exception:  # noqa: BLE001 - yt-dlp raises a wide range of errors
        return []

    candidates: list[Candidate] = []

    for entry in info.get("entries") or []:
        if not entry:
            continue

        title = str(entry.get("title") or "").strip()
        duration = float(entry.get("duration") or 0.0)

        if not title:
            continue

        candidates.append(Candidate(
            artist=_clean_uploader(str(entry.get("uploader") or entry.get("channel") or "")),
            title=title,
            album="",
            duration=duration,
            preview_url="",
            artwork=str(entry.get("thumbnail") or ""),
            store_url=str(entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"),
            source="youtube",
        ))

    return candidates


_STREAM_CACHE: dict[str, tuple[str, float]] = {}
STREAM_TTL = 4 * 60 * 60


def youtube_stream(candidate: Candidate, timeout: float = 20.0) -> str:
    """Resolve a playable audio URL for a YouTube candidate (expires after hours)."""

    if candidate.stream_url:
        return candidate.stream_url

    import time as _time

    cached = _STREAM_CACHE.get(candidate.store_url)

    if cached and cached[1] > _time.time():
        candidate.stream_url = cached[0]
        return candidate.stream_url

    try:
        import yt_dlp

    except ImportError as error:
        raise RuntimeError("yt-dlp is not installed") from error

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "socket_timeout": timeout,
        "format": "bestaudio/best",
    }

    url = candidate.store_url or f"https://www.youtube.com/watch?v={candidate.store_url}"

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    stream = info.get("url") or ""

    if not stream:
        for fmt in reversed(info.get("formats") or []):
            if fmt.get("acodec") not in (None, "none") and fmt.get("url"):
                stream = fmt["url"]
                break

    if not stream:
        raise RuntimeError("no audio stream found")

    candidate.stream_url = stream
    _STREAM_CACHE[candidate.store_url] = (stream, _time.time() + STREAM_TTL)
    return stream


def score_candidate(candidate: Candidate, parsed: ParsedName,
                    expected_duration: float = 0.0) -> float:
    """Blend artist/title similarity with a duration check."""

    title_score = similarity(parsed.title, candidate.title)

    # YouTube titles usually carry the artist ("Chris Stussy - Desire"), and
    # channels are inconsistent, so score the combined title+artist text too.
    haystack = f"{candidate.title} {candidate.artist}".strip()
    content_score = similarity(f"{parsed.artist} {parsed.title}".strip(), haystack)

    if parsed.artist and candidate.artist:
        artist_score = similarity(parsed.artist, candidate.artist)
    else:
        artist_score = content_score

    score = (title_score * 0.45) + (content_score * 0.35) + (artist_score * 0.2)

    if expected_duration and candidate.duration:
        delta = abs(candidate.duration - expected_duration)
        # Duration is the strongest disambiguator between an original, an edit
        # and an unrelated song with a similar name.
        if delta <= 3:
            score += 0.25
        elif delta <= 10:
            score += 0.12
        elif delta <= 30:
            score += 0.02
        elif delta <= 60:
            score -= 0.15
        else:
            score -= 0.35

    return max(0.0, min(1.0, score))


def resolve(filename: str, expected_duration: float = 0.0,
            minimum_score: float = 0.45, limit: int = 8,
            sources: tuple[str, ...] = ("itunes", "youtube"),
            timeout: float = 15.0) -> list[Candidate]:
    """Return catalogue matches for a filename, best first.

    iTunes answers in a few hundred milliseconds and has clean metadata;
    YouTube has many more bootlegs, edits and white labels but takes seconds.
    Both are queried concurrently so the YouTube breadth does not delay the
    fast path.
    """

    from concurrent.futures import ThreadPoolExecutor

    parsed = parse_filename(filename)
    primary = f"{parsed.artist} {parsed.title}".strip() if parsed.artist else parsed.title
    queries = [primary]

    if parsed.title != primary:
        queries.append(parsed.title)

    tasks = []

    for query in queries:
        if "itunes" in sources:
            tasks.append(("itunes", query))

    if "youtube" in sources:
        tasks.append(("youtube", primary))

    def run(task):

        kind, query = task

        try:
            if kind == "itunes":
                return search_itunes(query, limit=limit)

            return search_youtube(query, limit=limit)

        except Exception:  # noqa: BLE001 - a dead source must not kill the resolve
            return []

    results: list[Candidate] = []

    with ThreadPoolExecutor(max_workers=len(tasks) or 1) as pool:
        for batch in pool.map(run, tasks):
            results.extend(batch)

    seen: dict[tuple[str, str], Candidate] = {}

    for candidate in results:
        key = (candidate.artist.lower(), candidate.title.lower())

        if key in seen:
            continue

        candidate.score = score_candidate(candidate, parsed, expected_duration)
        seen[key] = candidate

    ranked = sorted(seen.values(), key=lambda item: item.score, reverse=True)
    return [candidate for candidate in ranked if candidate.score >= minimum_score]


def lookup_preview(filename: str, expected_duration: float = 0.0,
                   sources: tuple[str, ...] = ("itunes", "youtube")) -> Candidate | None:
    matches = resolve(filename, expected_duration=expected_duration, sources=sources)
    return matches[0] if matches else None
