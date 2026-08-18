"""Check whether anyone picked anything, without loading the heavy toolchain.

Runs on every scheduled publish attempt, so it must stay cheap: it imports only
the Discord client, never the renderer, and needs no browser. The expensive
install of Playwright and Chromium happens downstream only when this says there
is work to do.

Writes has_picks / picks to $GITHUB_OUTPUT when running in Actions.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from discord_client import Discord

STATE = Path(__file__).resolve().parent / "state"
DIGITS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def emit(has_picks: bool, picks: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"has_picks={'true' if has_picks else 'false'}\n")
            f.write(f"picks={picks}\n")
    print(f"has_picks={has_picks} picks={picks or '-'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    path = STATE / f"review-{today.isoformat()}.json"
    if not path.exists():
        print("本日のレビューがありません")
        return emit(False, "")

    st = json.loads(path.read_text(encoding="utf-8"))
    cands = st.get("candidates", [])
    if not cands:
        print("候補なし")
        return emit(False, "")

    numbers = DIGITS[: len(cands)]
    chosen = Discord().picked(
        st["message_id"], numbers + ["⏭"], channel_id=st.get("channel_id")
    )
    if "⏭" in chosen:
        print("全スキップが選択されています")
        return emit(False, "")

    done = set(st.get("delivered", []))
    idx = [numbers.index(e) + 1 for e in chosen if e in numbers]
    idx = [n for n in idx if cands[n - 1]["id"] not in done]

    if not idx:
        print("未配信の選択はありません")
        return emit(False, "")

    print(f"未配信の選択: {idx}")
    emit(True, ",".join(str(n) for n in sorted(idx)))


if __name__ == "__main__":
    main()
