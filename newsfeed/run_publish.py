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

import caption as cap
import deliver
import overrides as ov
from discord_client import Discord

STATE = Path(__file__).resolve().parent / "state"


def main() -> None:
    ap = argparse.ArgumentParser(description="Deliver the picked cards to Discord")
    ap.add_argument("--date", default=None)
    ap.add_argument("--out", default="out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-body", action="store_true",
                    help="本文を生成しない（見出しのみのキャプション）")
    ap.add_argument("--no-article", action="store_true",
                    help="本文生成時に記事ページを取得しない")
    ap.add_argument("--no-overrides", action="store_true",
                    help="返信による見出し/画像の差し替えを読まない")
    ap.add_argument(
        "--pick",
        default="",
        help="リアクションの代わりに番号を指定 (例: 1,3)。テスト用",
    )
    ap.add_argument(
        "--title",
        action="append",
        default=[],
        metavar="N=見出し",
        help="見出しを差し替える。複数回指定可 (例: --title 3=新しい見出し)",
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

    # Pull in any replacement headline or image a human posted as a reply,
    # keyed by the same numbers shown in the review list.
    edits = {} if args.no_overrides else ov.collect_overrides(
        dc, st["message_id"], len(cands), Path(args.out),
        channel_id=st.get("channel_id"),
    )
    # Titles given on the command line win over anything posted in Discord:
    # they were typed just now, with the card already in view.
    for spec in args.title:
        if "=" not in spec:
            raise SystemExit(f"--title の書式が違います: {spec!r} (例: 3=新しい見出し)")
        num, text = spec.split("=", 1)
        try:
            i = int(num.strip()) - 1
        except ValueError:
            raise SystemExit(f"--title の番号が数字ではありません: {num!r}")
        if not 0 <= i < len(cands):
            raise SystemExit(f"--title の番号が範囲外です: {num} (候補は1〜{len(cands)})")
        edits.setdefault(i, {"headline": None, "photo": None})["headline"] = text.strip()

    ov.apply_overrides(cands, edits)

    approved = [cands[i] for i in idx]
    for c in approved:
        c.setdefault("date", today.isoformat())

    # Bodies are written here, for the picked items only — a handful a day
    # rather than the whole batch.
    if not args.no_body:
        for c in approved:
            print(f"  本文を生成中: {c['headline'][:24]}…")
            c["body"] = cap.generate(c, use_article=not args.no_article)

    pairs = deliver.render(approved, out_dir=args.out)
    flats = [f for f, _ in pairs]
    messages = deliver.build(approved, flats, today)

    for (flat, overlay), msg in zip(pairs, messages):
        dc.post_with_files(msg, [flat, overlay])

    st["delivered"] = sorted(done | {c["id"] for c in approved})
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(approved)}件を配信しました。")


if __name__ == "__main__":
    main()
