"""Delivery stage — turns approved candidates into things a human can post.

There is no Instagram API call anywhere in this pipeline. The output is a card
image plus copy-pasteable text, delivered to Discord; posting and scheduling
happen by hand in Meta Business Suite. That removes App Review from the
critical path and makes a mis-post structurally impossible.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"
sys.path.insert(0, str(CARDS_DIR))

from config import POST_WINDOWS  # noqa: E402


def render(candidates: list[dict], out_dir: str | Path) -> list[Path]:
    """Render one card per candidate using the card renderer."""
    from render import render_cards  # imported late so config stays importable

    items = [
        {
            "name": f"{i + 1:02d}_{c['id']}",
            "headline": c["headline"],
            "category": c["category"],
            "keywords": c.get("keywords", []),
            "date": c.get("date", date.today().isoformat()),
        }
        for i, c in enumerate(candidates)
    ]
    return render_cards(items, out_dir=out_dir)


def next_windows(start: date, count: int) -> list[str]:
    """Next `count` publishing slots from `start`, one per day at most.

    The daily cap is enforced here rather than downstream: an approved post
    that hits the cap must move to the next day, never be discarded.
    """
    slots, day = [], start
    for _ in range(60):
        if len(slots) >= count:
            break
        for t in POST_WINDOWS.get(day.isoweekday(), []):
            if len(slots) < count:
                slots.append(f"{day.isoformat()} {t}")
        day += timedelta(days=1)
    return slots


def hashtags(c: dict) -> str:
    """Keywords plus a fixed tail. Kept separate from the caption so it can be
    pasted as the first comment, which reads cleaner than a tag-stuffed body."""
    tags = [f"#{k.lstrip('#')}" for k in c.get("keywords", [])]
    tail = ["#車好きと繋がりたい", "#クルマ好き", "#REVO"]
    return " ".join(tags + tail)


def caption(c: dict) -> str:
    return (
        f"{c['headline']}\n\n"
        f"{(c.get('summary') or '')[:120]}\n\n"
        f"詳細は{c.get('source', '各媒体')}の記事より。\n"
        f"REVOでは全国のカースポットとイベントをマップで確認できます。\n"
        f"プロフィールのリンクから。"
    )


def discord_message(c: dict, card: Path, slot: str) -> str:
    """One message per approved card, formatted for copy-paste on a phone."""
    video = "🎬 公式動画あり" if c.get("video_official") else "📷 静止画のみ"
    return "\n".join(
        [
            f"**【投稿用】{c['category']}｜{c['score']}点**  {video}",
            f"`{card.name}`",
            "",
            "▼ キャプション",
            "```",
            caption(c),
            "```",
            "▼ ハッシュタグ（1コメント目）",
            "```",
            hashtags(c),
            "```",
            f"▼ 推奨投稿: **{slot}**",
            f"▼ 出典: {c.get('source', '')} — {c.get('url', 'URL未取得')}",
        ]
    )


DIGITS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
DISCORD_LIMIT = 2000


def _stamp(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_JA[d.weekday()]})"


def daily_review(
    candidates: list[dict],
    day: date,
    collected: int,
    dropped: dict[str, int],
) -> list[str]:
    """The day's candidate list, for a human to pick from with reactions.

    Everything that makes the batch identifiable as *today's* sits in the
    header: the date, the weekday, and the funnel counts. Without those a
    Discord backlog of these messages is unreadable a week later.
    """
    n_dropped = sum(dropped.values())
    head = [
        f"# 📅 {_stamp(day)} のニュース",
        f"`収集 {collected}件 → 除外 {n_dropped}件 → 候補 {len(candidates)}件`",
    ]

    if not candidates:
        head += [
            "**本日は候補なしです。**",
            "閾値を超える記事がありませんでした。投稿を見送ってください。",
        ]
        return ["\n".join(head)]

    blocks = []
    for i, c in enumerate(candidates[: len(DIGITS)]):
        marks = []
        if (c.get("region") or c.get("region_hint")) == "WORLD":
            marks.append("🌍 海外")
        if c.get("video_official"):
            marks.append("🎬 公式動画")
        mark = ("　" + " ・ ".join(marks)) if marks else ""
        blocks.append(
            "\n".join(
                [
                    f"**{DIGITS[i]}　{c['score']}点　{c['category']}**{mark}",
                    f"{c['headline']}",
                    f"-# {c.get('source', '')} ・ {c.get('reason', '')}",
                    f"-# {c.get('url') or 'URL未取得'}",
                ]
            )
        )

    tail = [
        "",
        "──────────",
        "数字でリアクション → カード生成 ／ ⏭ 全スキップ",
        "-# 除外内訳: "
        + "・".join(f"{k} {v}" for k, v in sorted(dropped.items()))
        + f"　｜　投稿枠 {next_windows(day, 1)[0] if next_windows(day, 1) else '—'}",
    ]

    # Discord caps a message at 2000 characters; split on block boundaries
    # rather than mid-item so every part stays readable on its own.
    messages, cur = [], list(head)
    for b in blocks:
        candidate = "\n\n".join(cur + [b])
        if len(candidate) > DISCORD_LIMIT - 300 and len(cur) > len(head):
            messages.append("\n\n".join(cur))
            cur = [f"# 📅 {_stamp(day)} のニュース（続き）", b]
        else:
            cur.append(b)
    cur.append("\n".join(tail))
    messages.append("\n\n".join(cur))
    return messages


def build(candidates: list[dict], cards: list[Path], today: date) -> list[str]:
    """Assemble the Discord messages, enforcing the posting caps."""
    slots = next_windows(today, len(candidates))
    if len(slots) < len(candidates):
        raise RuntimeError(
            f"承認{len(candidates)}件に対し枠が{len(slots)}件しか確保できませんでした"
        )
    return [
        discord_message(c, card, slot)
        for c, card, slot in zip(candidates, cards, slots)
    ]
