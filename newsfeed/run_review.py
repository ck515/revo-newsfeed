"""Post the day's candidate list to Discord and seed the number reactions.

Run this once a day. It saves the message id and the candidate list to
state/review-<date>.json so run_publish.py can pick up where this left off.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import deliver
import score as scoring
from config import MAX_CANDIDATES_PER_DAY
from discord_client import Discord
from screen import screen, summarise

STATE = Path(__file__).resolve().parent / "state"


def gather(args, today: date):
    if args.live:
        from collect import collect, load_seen, save_seen

        items, notes = collect()
        for n in notes:
            print("  " + n)
        seen = load_seen()
        save_seen(seen | {i["id"] for i in items})
    else:
        items = json.loads(Path(args.feed).read_text(encoding="utf-8"))

    kept, dropped = screen(items)
    if not kept:
        return items, [], summarise(dropped)

    raw = (
        scoring.score_via_api(kept)
        if args.live
        else scoring.score_from_file(args.scores)
    )
    scored = scoring.merge(kept, raw)

    fixes = scoring.repair(scored)
    if fixes:
        print("出力契約の修復:")
        for f in fixes:
            print("  · " + f)

    # Anything still broken after repair is a bug in repair(), not in the model.
    problems = scoring.validate(scored)
    if problems:
        print("修復できなかった違反:")
        for p in problems:
            print("  ! " + p)
        if args.strict:
            raise SystemExit("中断しました（--strict）")

    cands = scoring.above_threshold(scored)[:MAX_CANDIDATES_PER_DAY]
    return items, cands, summarise(dropped)


def main() -> None:
    ap = argparse.ArgumentParser(description="Post the daily review to Discord")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--feed", default="fixtures/feed.json")
    ap.add_argument("--scores", default="fixtures/scores.json")
    ap.add_argument("--date", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="送信せずペイロードを表示")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    items, cands, dropped = gather(args, today)

    dc = Discord(dry_run=args.dry_run)
    messages = deliver.daily_review(cands, today, len(items), dropped)

    # Reactions go on the last message, which is the one carrying the footer
    # and therefore the one a reader is looking at when they decide.
    posted = [dc.post(m) for m in messages]
    target = posted[-1]["id"]
    # When posting through the webhook the channel id is only known from the
    # response, so take it from there rather than from the environment.
    channel = posted[-1].get("channel_id") or dc.channel_id

    emojis = deliver.DIGITS[: len(cands)] + (["⏭"] if cands else [])
    for e in emojis:
        dc.add_reaction(target, e, channel_id=channel)

    STATE.mkdir(parents=True, exist_ok=True)
    out = STATE / f"review-{today.isoformat()}.json"
    out.write_text(
        json.dumps(
            {
                "date": today.isoformat(),
                "message_id": target,
                "channel_id": channel,
                "message_ids": [p["id"] for p in posted],
                "emojis": emojis,
                "candidates": cands,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n候補 {len(cands)}件を投稿しました。message_id={target}")
    print(f"状態を保存: {out}")


if __name__ == "__main__":
    main()
