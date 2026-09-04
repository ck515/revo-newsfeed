"""Decide what this run should do, from state rather than from the clock.

The previous design keyed the phase off the cron string: one entry meant
"review", anything else meant "publish". That broke twice. Changing the review
time meant editing the schedule *and* the string it was compared against, and
editing only one left the daily run silently doing the wrong job. It also meant
that if GitHub skipped or delayed that single daily cron — which it does under
load — the review simply never happened and the day passed with no candidates.

So the schedule no longer carries any meaning. One five-minute poll runs all
day and asks a different question: has today's review been written yet? If not,
and it is past the hour we want it, write it. Otherwise look for reactions.

A missed slot is picked up on the next poll instead of being lost for the day.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = Path(__file__).resolve().parent / "state"
JST = timezone(timedelta(hours=9))

# The hour, JST, at or after which the day's review may run. The poll fires all
# day, so this is the earliest acceptable time rather than an exact one.
REVIEW_HOUR = 12


def decide(now: datetime | None = None) -> tuple[str, str]:
    """Returns (phase, reason)."""
    now = now or datetime.now(JST)
    today = now.date().isoformat()
    review_file = STATE / f"review-{today}.json"

    if review_file.exists():
        return "publish", f"{today} のレビューは実行済み"
    if now.hour < REVIEW_HOUR:
        return "publish", f"{now:%H:%M} — レビューは{REVIEW_HOUR}時以降"
    return "review", f"{today} のレビュー未実行（{now:%H:%M}）"


def main() -> None:
    phase, reason = decide()
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"name={phase}\n")
    print(f"phase={phase}  ({reason})")


if __name__ == "__main__":
    main()
