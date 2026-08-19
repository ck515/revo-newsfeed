"""Build a week's posts from one spec file.

    python weekly.py --init 2026-W35      # 雛形を作る
    python weekly.py posts/2026-W35.yml   # 全カードを書き出す

One YAML per week, edited by hand, kept in the repo. Photos are referenced by
filename from a photos/ folder. Output is a numbered folder per week, so the
upload order in a carousel is fixed by the filenames and never has to be
remembered.

Why a file and not a prompt or a form: titles and photo choices change every
week and need to be revised, diffed and reused. A spec that sits in the repo
can be edited before it is built, corrected after, and copied forward to next
week — none of which a one-shot command line can do.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
POSTS = BASE / "posts"
PHOTOS = BASE / "photos"

import layouts as L  # noqa: E402
from render import render_card  # noqa: E402

TEMPLATE = """# {week} の投稿
# 写真は photos/ からのファイル名で指定します。
# posts の並び順がそのままカルーセルの順番になります。

week: {week}
date: {date}

posts:

  # ---- イベントまとめ（表紙 + 中面）--------------------------------
  - type: cover_events
    photo: CHANGE_ME.jpg        # photos/ に置いたファイル名
    month: {month}
    count: 4
    area: 首都圏・東海
    title: 今月のカーイベント

  - type: events
    month: {month}
    area: 首都圏・東海
    events:
      - day: "06"
        wd: SUN
        name: イベント名
        place: 神奈川・大黒PA

  # ---- 機能紹介（表紙 + 中面）--------------------------------------
  # - type: cover_feature
  #   photo: CHANGE_ME.jpg
  #   name_en: DRIVE LOG
  #   name_ja: ドライブログ
  #   hook: 走った道が、そのまま1枚のカードになります。
  #
  # - type: feature
  #   name_en: DRIVE LOG
  #   name_ja: ドライブログ
  #   lead: 走行を記録して、あとから振り返れる機能です。
  #   points:
  #     - ルートが地図として残る
  #     - 立ち寄ったスポットが紐づく
  #     - 1枚のカードとして共有できる

  # ---- 進捗・改善報告 ----------------------------------------------
  # - type: roadmap
  #   period: Q3
  #   period_label: 2026年 第3四半期
  #   phases:
  #     - {{text: 実績・称号システムの実装, status: now}}
  #     - {{text: イベント連携の開放, status: next}}
  #
  # - type: changelog
  #   version: v1.4
  #   when: 8月アップデート
  #   items:
  #     - {{tag: NEW, text: 追加した機能}}
  #     - {{tag: FIX, text: 直した不具合}}

  # ---- ニュース単発 --------------------------------------------------
  # - type: news
  #   category: PARTS
  #   headline: 見出し
  #   keywords: [キーワード1, キーワード2]

caption: |
  ここにキャプションを書きます。
  空にしておくと caption.txt は作られません。

hashtags: >
  #車好きと繋がりたい #クルマ好き #REVO
"""


def _photo(spec: dict, key: str = "photo") -> str | None:
    name = spec.get(key)
    if not name:
        return None
    p = PHOTOS / name
    if not p.exists():
        raise SystemExit(
            f"写真が見つかりません: {p}\n"
            f"  photos/ に置いたファイル名を指定してください。"
        )
    return str(p)


def build_one(spec: dict, out: Path, idx: int, when: str, transparent: bool) -> Path:
    """Render one post. Filenames are numbered so carousel order is fixed."""
    t = spec.get("type")
    suffix = "_overlay" if transparent else ""
    name = f"{idx:02d}_{t}{suffix}.png"
    dest = out / name
    common = {"date_str": spec.get("date", when), "transparent": transparent,
              "out": dest}

    if t == "cover_events":
        L.render_cover_events(
            month=spec["month"], count=spec["count"], area=spec.get("area", ""),
            photo=_photo(spec), title=spec.get("title", "今月のカーイベント"),
            year=spec.get("year"), overlay=spec.get("overlay", 0.30), **common)
    elif t == "events":
        L.render_events(month=spec["month"], events=spec["events"],
                        area=spec.get("area", ""), **common)
    elif t == "cover_feature":
        L.render_cover_feature(
            name_en=spec["name_en"], name_ja=spec["name_ja"], hook=spec["hook"],
            photo=_photo(spec), kicker=spec.get("kicker", "新機能"),
            overlay=spec.get("overlay", 0.30), **common)
    elif t == "feature":
        L.render_feature(name_en=spec["name_en"], name_ja=spec["name_ja"],
                         lead=spec["lead"], points=spec["points"], **common)
    elif t == "roadmap":
        L.render_roadmap(period=spec["period"], period_label=spec["period_label"],
                         phases=spec["phases"], segments=spec.get("segments"), **common)
    elif t == "changelog":
        L.render_changelog(version=spec["version"], items=spec["items"],
                           when=spec.get("when", ""), **common)
    elif t == "news":
        render_card(headline=spec["headline"], category=spec.get("category", "DEBUT"),
                    keywords=spec.get("keywords", []),
                    photo=_photo(spec), overlay=spec.get("overlay", 0.42),
                    date_str=spec.get("date", when), transparent=transparent,
                    out=dest)
    else:
        raise SystemExit(f"未知の type: {t!r}")
    return dest


def build(path: Path, overlays: bool) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    week = str(doc.get("week") or path.stem)
    when = str(doc.get("date") or date.today().isoformat())
    posts = doc.get("posts") or []
    if not posts:
        raise SystemExit("posts が空です")

    out = BASE / "out" / week
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    made = []
    for i, spec in enumerate(posts, 1):
        made.append(build_one(spec, out, i, when, transparent=False))
        print(f"  {made[-1].name}")
        if overlays:
            made.append(build_one(spec, out, i, when, transparent=True))
            print(f"  {made[-1].name}")

    caption = (doc.get("caption") or "").strip()
    tags = (doc.get("hashtags") or "").strip()
    if caption or tags:
        text = caption + ("\n\n" + tags if tags else "") + "\n"
        (out / "caption.txt").write_text(text, encoding="utf-8")
        print("  caption.txt")

    print(f"\n{len(made)}枚を書き出しました → {out}")


def init(week: str) -> None:
    POSTS.mkdir(parents=True, exist_ok=True)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    dest = POSTS / f"{week}.yml"
    if dest.exists():
        raise SystemExit(f"すでにあります: {dest}")
    try:
        d = datetime.strptime(week + "-1", "%G-W%V-%u").date()
    except ValueError:
        d = date.today()
    dest.write_text(
        TEMPLATE.format(week=week, date=d.isoformat(), month=d.month),
        encoding="utf-8",
    )
    print(f"作成しました: {dest}\n写真は {PHOTOS} に置いてください。")


def main() -> None:
    ap = argparse.ArgumentParser(description="週次の投稿カードを書き出す")
    ap.add_argument("spec", nargs="?", help="posts/2026-W35.yml")
    ap.add_argument("--init", metavar="2026-W35", help="雛形を作る")
    ap.add_argument("--no-overlay", action="store_true",
                    help="背景透過版を書き出さない")
    a = ap.parse_args()

    if a.init:
        return init(a.init)
    if not a.spec:
        ap.error("spec か --init のどちらかを指定してください")
    p = Path(a.spec)
    if not p.exists():
        p = POSTS / a.spec
    if not p.exists():
        raise SystemExit(f"見つかりません: {a.spec}")
    build(p, overlays=not a.no_overlay)


if __name__ == "__main__":
    sys.exit(main())
