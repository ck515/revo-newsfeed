"""REVO news pipeline.

  collect (RSS) -> screen (mechanical) -> score (Claude) -> candidates
                -> [human picks in Discord] -> render cards -> Discord delivery
                -> [human posts via Meta Business Suite]

Two human gates, both mandatory: picking which stories run, and approving the
rendered card. Nothing publishes on its own.

Usage
    python pipeline.py --feed fixtures/feed.json --scores fixtures/scores.json
        Full run from fixtures. No network, no API key. Use this to check
        behaviour after editing the filter or the prompt.

    python pipeline.py --live
        Fetch RSS and score via the API. Needs ANTHROPIC_API_KEY.

    python pipeline.py --live --no-score
        Fetch and screen only. Run this for a week first to see the volume
        before spending anything on scoring.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import deliver
import score as scoring
from config import MAX_CANDIDATES_PER_DAY, SCORE_THRESHOLD
from screen import screen, summarise

STATE = Path(__file__).resolve().parent / "state"


def run(args) -> None:
    today = date.fromisoformat(args.date) if args.date else date.today()

    # ---- collect ----------------------------------------------------------
    if args.live:
        from collect import collect, load_seen, save_seen

        items, notes = collect()
        print("■ 収集")
        for n in notes:
            print("  " + n)
    else:
        items = json.loads(Path(args.feed).read_text(encoding="utf-8"))
        print(f"■ 収集（fixture） {len(items)}件")
    if not items:
        print("新規記事なし。終了します。")
        return

    # ---- screen -----------------------------------------------------------
    kept, dropped = screen(items)
    print(f"\n■ 機械的除外  通過 {len(kept)} / 除外 {len(dropped)}")
    for reason, n in sorted(summarise(dropped).items()):
        print(f"  {reason}: {n}件")
    if args.verbose:
        for d in dropped:
            print(f"    [{d['reason']}] {d['title'][:50]}  ← {' '.join(d['matched'])}")
    if not kept:
        print("通過なし。終了します。")
        return

    if args.no_score:
        STATE.mkdir(parents=True, exist_ok=True)
        out = STATE / f"screened-{today.isoformat()}.json"
        out.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n採点はスキップしました。{out} に保存しました。")
        return

    # ---- score ------------------------------------------------------------
    raw = (
        scoring.score_via_api(kept)
        if args.live
        else scoring.score_from_file(args.scores)
    )
    scored = scoring.merge(kept, raw)

    fixes = scoring.repair(scored)
    problems = scoring.validate(scored)
    print(f"\n■ 採点  {len(scored)}件")
    for f in fixes:
        print("  · " + f)
    if problems:
        print("  出力契約の違反:")
        for p in problems:
            print("   ! " + p)
        if args.strict:
            raise SystemExit("出力契約に違反があるため中断しました（--strict）")
    else:
        print("  出力契約: 問題なし")

    if args.verbose:
        for s in scored:
            print(f"    {s['score']:2d} [{s['category'] or '—':5s}] {s['headline']}")

    passed = scoring.above_threshold(scored)
    cands = passed[:MAX_CANDIDATES_PER_DAY]

    # ---- daily review -----------------------------------------------------
    # This is the day's list as it appears in Discord. In production the run
    # ends here and waits for a human reaction; nothing downstream happens on
    # its own.
    review = deliver.daily_review(cands, today, len(items), summarise(dropped))
    print("\n■ Discord 日次レビュー")
    for m in review:
        print("\n" + "=" * 64)
        print(m)
        print("=" * 64 + f"  ({len(m)}字)")

    if not args.approve_top:
        return

    approved = cands[: args.approve_top]
    for c in approved:
        c.setdefault("date", today.isoformat())
    cards = deliver.render(approved, out_dir=args.out)
    msgs = deliver.build(approved, cards, today)
    print(f"\n■ 納品  カード {len(cards)}枚 / メッセージ {len(msgs)}件 → {args.out}")
    for m in msgs:
        print("\n" + "-" * 64 + "\n" + m)


def main() -> None:
    ap = argparse.ArgumentParser(description="REVO news pipeline")
    ap.add_argument("--live", action="store_true", help="RSS取得とAPI採点を実行")
    ap.add_argument("--feed", default="fixtures/feed.json")
    ap.add_argument("--scores", default="fixtures/scores.json")
    ap.add_argument("--no-score", action="store_true", help="収集と除外のみ")
    ap.add_argument("--approve-top", type=int, default=0, help="上位N件を承認済みとして納品")
    ap.add_argument("--out", default="out")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD")
    ap.add_argument("--strict", action="store_true", help="契約違反で中断")
    ap.add_argument("-v", "--verbose", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
