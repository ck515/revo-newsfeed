"""Collection stage — fetch and normalise RSS entries.

Deliberately tolerant: one dead feed must not stop the run. But a feed that
returns zero entries is reported, because a silently dead feed is
indistinguishable from a quiet news day and will just look like the pipeline
has stopped working.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from config import SOURCES

SEEN_PATH = Path(__file__).resolve().parent / "state" / "seen.json"


def _item_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:10]


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _image_url(entry) -> str:
    """Best-effort article image from the feed entry itself.

    Only used when CARD_BACKGROUND is "article". Feeds expose this in several
    places depending on the CMS, so try each rather than assuming one.
    """
    for key in ("media_content", "media_thumbnail"):
        vals = getattr(entry, key, None) or []
        for v in vals:
            url = v.get("url") if isinstance(v, dict) else None
            if url:
                return url
    for link in getattr(entry, "links", []) or []:
        if str(link.get("type", "")).startswith("image/") and link.get("href"):
            return link["href"]
    blob = str(getattr(entry, "summary", "")) + str(getattr(entry, "content", ""))
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', blob)
    return m.group(1) if m else ""


def _has_video(entry) -> bool:
    """Cheap check for an embedded video. Only a hint; the human decides."""
    blob = " ".join(
        str(getattr(entry, k, "")) for k in ("summary", "content", "links")
    ).lower()
    return any(m in blob for m in ("youtube.com/embed", "youtu.be", "<video", "player.vimeo"))


def load_seen() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))


def save_seen(ids: set[str], keep: int = 2000) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(
        json.dumps(sorted(ids)[-keep:], ensure_ascii=False), encoding="utf-8"
    )


def collect(sources: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """Returns (new items, per-source notes)."""
    import feedparser

    sources = sources or SOURCES
    seen = load_seen()
    items, notes = [], []

    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
        except Exception as e:
            notes.append(f"{src['name']}: 取得失敗 {e}")
            continue

        entries = getattr(feed, "entries", []) or []
        if not entries:
            notes.append(f"{src['name']}: 0件（フィードのURLを確認してください）")
            continue

        fresh = 0
        for e in entries:
            url = getattr(e, "link", "") or ""
            title = _strip_html(getattr(e, "title", ""))
            if not title:
                continue
            iid = _item_id(url, title)
            if iid in seen:
                continue
            items.append(
                {
                    "id": iid,
                    "source": src["name"],
                    "weight": src.get("weight", 1.0),
                    "url": url,
                    "title": title,
                    "summary": _strip_html(getattr(e, "summary", ""))[:600],
                    "published": getattr(e, "published", "") or "",
                    "has_video": _has_video(e),
                    "image_url": _image_url(e),
                }
            )
            fresh += 1
        notes.append(f"{src['name']}: {fresh}件（全{len(entries)}件）")

    return items, notes
