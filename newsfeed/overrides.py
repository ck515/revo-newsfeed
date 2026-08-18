"""Read per-card overrides a human posted in Discord.

The model's headline is a first draft and the auto-picked background is a
guess, so both need a way to be corrected without leaving the app. The
correction channel is the same place the choice was made: reply to the review
message with the card's number, and optionally a replacement headline, and
optionally an attached image.

    3                        -> card 3, image attached, headline unchanged
    3 筑波1分6秒台のケンメリ    -> card 3, headline replaced
    3 新しい見出し + 画像添付   -> both

Only messages that reply to the review message are read, so ordinary chatter in
the channel is never mistaken for an instruction.
"""

from __future__ import annotations

import re
from pathlib import Path

# A leading number, then optionally the rest of the line as a new headline.
OVERRIDE_RE = re.compile(r"^\s*(\d{1,2})\s*(.*)$", re.S)
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp")


def _is_image(att: dict) -> bool:
    name = (att.get("filename") or "").lower()
    ctype = (att.get("content_type") or "").lower()
    return ctype.startswith("image/") or name.endswith(IMAGE_TYPES)


def collect_overrides(
    dc, review_message_id: str, count: int, out_dir: Path,
    channel_id: str | None = None,
) -> dict[int, dict]:
    """Return {card_index: {"headline": str|None, "photo": str|None}}.

    Indexes are zero-based to match the candidate list. Later replies win, so
    correcting a correction works the way anyone would expect.
    """
    out: dict[int, dict] = {}
    msgs = dc.recent_messages(limit=100, channel_id=channel_id)

    # Oldest first so a later reply overwrites an earlier one.
    for m in reversed(msgs):
        ref = (m.get("message_reference") or {}).get("message_id")
        if ref != review_message_id:
            continue
        match = OVERRIDE_RE.match(m.get("content") or "")
        if not match:
            continue
        n = int(match.group(1))
        if not 1 <= n <= count:
            print(f"  無視: 番号 {n} は候補の範囲外です")
            continue
        idx = n - 1
        entry = out.setdefault(idx, {"headline": None, "photo": None})

        text = match.group(2).strip()
        if text:
            entry["headline"] = text

        for att in m.get("attachments", []):
            if _is_image(att):
                dest = out_dir / "_bg" / f"override_{idx + 1}{Path(att['filename']).suffix}"
                got = dc.download(att["url"], dest)
                if got:
                    entry["photo"] = str(got)
                break

    for idx, e in sorted(out.items()):
        bits = []
        if e["headline"]:
            bits.append(f"見出し「{e['headline']}」")
        if e["photo"]:
            bits.append("画像あり")
        if bits:
            print(f"  上書き {idx + 1}: " + " / ".join(bits))
    return out


def apply_overrides(candidates: list[dict], overrides: dict[int, dict]) -> None:
    """Mutate candidates in place with whatever the human supplied."""
    for idx, o in overrides.items():
        if idx >= len(candidates):
            continue
        if o.get("headline"):
            candidates[idx]["headline"] = o["headline"]
        if o.get("photo"):
            candidates[idx]["photo_override"] = o["photo"]
