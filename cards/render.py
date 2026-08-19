"""
REVO news card renderer.

Renders 1080x1350 PNG cards for Instagram feed posts from a headline,
category and keyword list. Output is typography-only by default; a photo
is optional and should only be used with rights-cleared images.

    from render import render_card

    render_card(
        headline="新型シビックタイプR、マイナーチェンジで出力向上",
        category="MODEL",
        keywords=["シビックタイプR", "ホンダ", "JDM"],
        date="2026-08-18",
        out="out/civic.png",
    )

CLI:
    python render.py --headline "..." --category PARTS --keywords 86 BRZ 車高調
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

import brandmark

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE = BASE_DIR / "template.html"

WIDTH, HEIGHT = 1080, 1350

# Category labels. Latin labels are set in Saira Condensed (oblique);
# anything non-ASCII falls back to Noto Sans JP set upright, because
# skewed Japanese glyphs read as a rendering fault rather than a style.
CATEGORIES = {
    "DEBUT": "新型車の発表・改良",
    "PARTS": "パーツ・チューニング",
    "EVENT": "イベント・オフ会・走行会",
    "RACE": "モータースポーツ",
    "RETRO": "旧車・絶版車・市場動向",
}

# There is deliberately no catch-all category. On a news account every post is
# news, so a generic label carries no information — if a story fits none of the
# five above, that is the signal to drop the story rather than to label it.
DEFAULT_CATEGORY = "DEBUT"

MAX_KEYWORDS = 3

# ---------------------------------------------------------------------------
# Line breaking
#
# Chromium breaks Japanese between almost any two characters, so a headline
# like "走行会は8月23日に富士スピードウェイで開催" comes out split mid-word:
# "富" / "士", "開" / "催". Fixing that needs word boundaries, not regex.
#
# BudouX (Google's Japanese line-break model) supplies the phrase boundaries.
# Each phrase becomes a nowrap span, so breaks land only between phrases. A
# phrase wider than the column would overflow, so template.html un-protects
# over-wide phrases and falls back to breaking inside them — and the regex
# runs below act as a second layer so that dates and words still hold together
# when that happens.
# ---------------------------------------------------------------------------
try:
    import budoux

    _PARSER = budoux.load_default_japanese_parser()
except Exception:  # budoux missing: fall back to regex-only protection
    _PARSER = None

_COUNTERS = r"年月日時分秒台段型代人円kmKMhH%％"
# NOTE: the digit+counter group repeats, otherwise "8月23日" matches as two
# separate runs ("8月", "23日") and Chromium is free to break between them.
_TOKEN_RE = re.compile(
    rf"(?P<num>(?:[0-9０-９]+\s*[{_COUNTERS}]*)+)"
    r"|(?P<kata>[ァ-ヶー]+)"
    r"|(?P<latin>[A-Za-z][A-Za-z0-9&.\-]*)"
)
_KATA_CAP = 9
_LATIN_CAP = 14


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _fmt_date(date: str) -> str:
    """2026-08-18 -> 08.18  /  passes through anything else unchanged."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date.strip())
    return f"{m.group(2)}.{m.group(3)}" if m else date.strip()


def _mark_runs(text: str) -> str:
    """Escape text and wrap dates, katakana words and Latin words in spans."""
    out, pos = [], 0
    for m in _TOKEN_RE.finditer(text):
        out.append(html.escape(text[pos : m.start()]))
        run, kind = m.group(0), m.lastgroup
        cap = _KATA_CAP if kind == "kata" else _LATIN_CAP if kind == "latin" else 99
        esc = html.escape(run)
        out.append(
            f"<span class='nb' data-k='{kind}'>{esc}</span>" if len(run) <= cap else esc
        )
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _protect(text: str) -> str:
    """Segment into phrases and mark unbreakable runs inside each."""
    phrases = _PARSER.parse(text) if _PARSER else [text]
    return "".join(
        f"<span class='ph'>{_mark_runs(ph)}</span>" for ph in phrases if ph
    )


def _photo_block(photo: str | Path | None) -> tuple[str, str]:
    """Returns (html, wrap_class). Embeds the image as a data URI so the
    render never depends on the network."""
    if not photo:
        return "", ""
    p = Path(photo)
    if not p.exists():
        raise FileNotFoundError(f"photo not found: {p}")
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return (
        f'<div class="photo"><img src="data:{mime};base64,{b64}" alt=""></div>',
        "with-photo",
    )


def _keywords_html(keywords: list[str] | None) -> str:
    if not keywords:
        return ""
    out = []
    for kw in keywords[:MAX_KEYWORDS]:
        kw = kw.lstrip("#").strip()
        if kw:
            out.append(f'<span class="kw"><i>#</i>{html.escape(kw)}</span>')
    return "".join(out)


def render_card(
    headline: str,
    category: str = DEFAULT_CATEGORY,
    keywords: list[str] | None = None,
    date: str = "",
    date_str: str = "",   # alias, so weekly.py can pass one keyword to every renderer
    photo: str | Path | None = None,
    overlay: float = 0.42,
    logo_color: str = "white",
    transparent: bool = False,
    out: str | Path = "card.png",
) -> Path:
    """Render one card to PNG and return its path.

    headline    Japanese headline. Auto-sized; keep it under ~34 chars or the
                type drops below the readable floor for a feed thumbnail.
    category    Key from CATEGORIES ('DEBUT', 'PARTS', 'EVENT', 'RACE',
                'RETRO'), or any custom string. Keep custom labels to 4-6
                characters so the tag width stays consistent across the grid.
    keywords    Up to 3. Leading '#' optional.
    date        'YYYY-MM-DD' (rendered as MM.DD) or a literal string.
    photo       Optional local image path, rendered full-bleed behind the
                text under a dark scrim. Rights-cleared sources only.
    overlay     Scrim strength, 0-1. Raise it for bright or busy photos.
    logo_color  'white' (default) or 'accent'.
    transparent Render only the marks on a transparent background, for
                compositing over your own image in an editor. Any photo is
                dropped, since it would be replaced anyway.
    """
    date = date or date_str
    if not headline.strip():
        raise ValueError("headline is required")
    if logo_color not in ("white", "accent"):
        raise ValueError("logo_color must be 'white' or 'accent'")
    if not 0.0 <= overlay <= 1.0:
        raise ValueError("overlay must be between 0 and 1")

    category = category.strip() or DEFAULT_CATEGORY
    photo_html, wrap_class = _photo_block(photo)

    tpl = TEMPLATE.read_text(encoding="utf-8")
    filled = (
        tpl.replace("__CATEGORY__", html.escape(category))
        .replace("__TAG_CLASS__", "" if _is_ascii(category) else "jp")
        .replace("__PHOTO_BLOCK__", photo_html)
        .replace("__PHOTO_CLASS__", wrap_class)
        .replace("__HEADLINE__", _protect(headline.strip()))
        .replace("__KEYWORDS__", _keywords_html(keywords))
        .replace("__DATE__", html.escape(_fmt_date(date)))
        .replace("--overlay:0.42;", f"--overlay:{overlay};")
        .replace("__BODY_CLASS__", "transparent" if transparent else "")
    )
    filled = brandmark.apply(filled, logo_color)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write next to the template so the relative font URLs resolve.
    tmp = BASE_DIR / f".render_{out_path.stem}.html"
    tmp.write_text(filled, encoding="utf-8")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--font-render-hinting=none"])
            page = browser.new_page(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=1,
            )
            page.goto(tmp.as_uri())
            page.wait_for_function("document.body.dataset.ready === '1'")
            page.wait_for_timeout(120)  # let webfonts settle
            page.locator("#card").screenshot(
                path=str(out_path), omit_background=transparent
            )
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)

    return out_path


def render_cards(items: list[dict], out_dir: str | Path = "out") -> list[Path]:
    """Render many cards in one browser session.

    Each item takes the same keys as render_card() plus 'name', which becomes
    the filename. Use this for the monthly event carousel (name them 01_, 02_
    so the upload order is fixed) and for the daily news batch.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    paths: list[Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--font-render-hinting=none"])
        page = browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1
        )
        for i, it in enumerate(items):
            name = it.get("name") or f"card_{i + 1:02d}"
            category = (it.get("category") or DEFAULT_CATEGORY).strip()
            photo_html, wrap_class = _photo_block(it.get("photo"))
            filled = (
                tpl.replace("__CATEGORY__", html.escape(category))
                .replace("__TAG_CLASS__", "" if _is_ascii(category) else "jp")
                .replace("__PHOTO_BLOCK__", photo_html)
                .replace("__PHOTO_CLASS__", wrap_class)
                .replace("__HEADLINE__", _protect(it["headline"].strip()))
                .replace("__KEYWORDS__", _keywords_html(it.get("keywords")))
                .replace("__DATE__", html.escape(_fmt_date(it.get("date", ""))))
                .replace("--overlay:0.42;", f"--overlay:{it.get('overlay', 0.42)};")
                .replace(
                    "__BODY_CLASS__",
                    "transparent" if it.get("transparent") else "",
                )
            )
            filled = brandmark.apply(filled, it.get("logo_color", "white"))
            tmp = BASE_DIR / f".render_batch_{i}.html"
            tmp.write_text(filled, encoding="utf-8")
            try:
                page.goto(tmp.as_uri())
                page.wait_for_function("document.body.dataset.ready === '1'")
                page.wait_for_timeout(80)
                dest = out_dir / f"{name}.png"
                page.locator("#card").screenshot(
                    path=str(dest), omit_background=bool(it.get("transparent"))
                )
                paths.append(dest)
            finally:
                tmp.unlink(missing_ok=True)
        browser.close()
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a REVO news card.")
    ap.add_argument("--headline", required=True)
    ap.add_argument("--category", default=DEFAULT_CATEGORY,
                    choices=sorted(CATEGORIES))
    ap.add_argument("--keywords", nargs="*", default=[])
    ap.add_argument("--date", default="")
    ap.add_argument("--photo", default=None)
    ap.add_argument("--overlay", type=float, default=0.42)
    ap.add_argument("--logo-color", default="white", choices=["white", "accent"])
    ap.add_argument("--transparent", action="store_true",
                    help="背景透過PNGで出力（編集用）")
    ap.add_argument("--out", default="card.png")
    a = ap.parse_args()
    path = render_card(
        headline=a.headline,
        category=a.category,
        keywords=a.keywords,
        date=a.date,
        photo=a.photo,
        overlay=a.overlay,
        logo_color=a.logo_color,
        transparent=a.transparent,
        out=a.out,
    )
    print(path)


if __name__ == "__main__":
    main()
