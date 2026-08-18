"""Read the reactions on today's review, render the picked cards, upload them.

Run this after run_review.py, far enough behind that a human has had time to
look. Safe to run repeatedly: already-delivered items are recorded and skipped,
so a retry never double-posts.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import deliver
from discord_client import Discord

STATE = Path(__file__).resolve().parent / "state"


def main() -> None:
    ap = argparse.ArgumentParser(description="Deliver the picked cards to Discord")
    ap.add_argument("--date", default=None)
    ap.add_argument("--out", default="out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--pick",
        default="",
        help="リアクションの代わりに番号を指定 (例: 1,3)。テスト用",
    )
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    path = STATE / f"review-{today.isoformat()}.json"
    if not path.exists():
        raise SystemExit(f"{path} がありません。先に run_review.py を実行してください。")

    st = json.loads(path.read_text(encoding="utf-8"))
    cands = st["candidates"]
    if not cands:
        print("候補がありません。終了します。")
        return

    dc = Discord(dry_run=args.dry_run)

    if args.pick:
        idx = [int(n) - 1 for n in args.pick.split(",") if n.strip()]
    else:
        numbers = deliver.DIGITS[: len(cands)]
        chosen = dc.picked(
            st["message_id"], numbers + ["⏭"], channel_id=st.get("channel_id")
        )
        if "⏭" in chosen:
            print("全スキップが選択されました。終了します。")
            return
        idx = [numbers.index(e) for e in chosen if e in numbers]

    done = set(st.get("delivered", []))
    idx = [i for i in idx if 0 <= i < len(cands) and cands[i]["id"] not in done]
    if not idx:
        print("新たに配信する項目はありません。")
        return

    approved = [cands[i] for i in idx]
    for c in approved:
        c.setdefault("date", today.isoformat())

    cards = deliver.render(approved, out_dir=args.out)
    messages = deliver.build(approved, cards, today)

    for c, card, msg in zip(approved, cards, messages):
        dc.post_with_files(msg, [card])

    st["delivered"] = sorted(done | {c["id"] for c in approved})
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(approved)}件を配信しました。")


if __name__ == "__main__":
    main()
