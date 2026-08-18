"""Mechanical screening — runs before the model, never after.

Returns every item with a verdict attached rather than silently dropping, so
the reason a story vanished is always inspectable. Screening reads the title
and summary only; that is what an RSS entry reliably carries.
"""

from __future__ import annotations

from config import EXCLUDE, FOREIGN_MARKET


def screen_item(item: dict) -> dict:
    """Attach `kept`, `reason`, `matched` and `region_hint` to a copy."""
    text = f"{item.get('title', '')} {item.get('summary', '')}"

    for group, words in EXCLUDE.items():
        hits = [w for w in words if w in text]
        if hits:
            return {**item, "kept": False, "reason": group, "matched": hits}

    # Overseas stories are kept and merely flagged. Whether a Lamborghini
    # premiere matters to this readership is a judgement, and a keyword cannot
    # make it — that is the scoring layer's job. `region_hint` is only a
    # fallback for when the model does not return a region.
    foreign = [w for w in FOREIGN_MARKET if w in text]

    return {
        **item,
        "kept": True,
        "reason": None,
        "matched": [],
        "region_hint": "WORLD" if foreign else "JP",
    }


def screen(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a batch into (kept, dropped)."""
    judged = [screen_item(i) for i in items]
    return [i for i in judged if i["kept"]], [i for i in judged if not i["kept"]]


def summarise(dropped: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in dropped:
        counts[d["reason"]] = counts.get(d["reason"], 0) + 1
    return counts
