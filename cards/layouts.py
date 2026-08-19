"""REVO editorial card layouts.

Four post types that share the news card's design system — same palette, same
typefaces, same tag and footer — but differ in structure, because they answer
different questions:

    roadmap    どこまで進んだか      シフトインジケーター型の進捗バー
    changelog  何を直したか          整備記録簿型のログ
    feature    何ができるのか        パーツカタログ型の番号付き解説
    events     今月どこに行けるか    エントリーリスト型の日付表

    from layouts import render_roadmap, render_changelog, render_feature, render_events
"""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

import brandmark

BASE_DIR = Path(__file__).resolve().parent
LAYOUT_DIR = BASE_DIR / "layouts"
WIDTH, HEIGHT = 1080, 1350

MONTH_EN = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]
# Kept to four characters: "IN PROGRESS" wrapped onto a second line and pushed
# that row out of alignment with the rest of the column.
STATUS_LABEL = {"done": "DONE", "now": "NOW", "next": "NEXT"}


def _fmt_date(d: str) -> str:
    import re

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", (d or "").strip())
    return f"{m.group(2)}.{m.group(3)}" if m else (d or "").strip()


def _photo_html(photo: str | Path | None) -> str:
    """Full-bleed background, embedded as a data URI so a render never depends
    on the network. Covers assume a photo; without one they fall back to the
    flat background rather than failing."""
    import base64
    import mimetypes

    if not photo:
        return ""
    p = Path(photo)
    if not p.exists():
        raise FileNotFoundError(f"photo not found: {p}")
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<div class="photo"><img src="data:{mime};base64,{b64}" alt=""></div>'


def _shoot(template: str, fields: dict, out: Path, transparent: bool) -> Path:
    css = (LAYOUT_DIR / "_base.css").read_text(encoding="utf-8")
    tpl = (LAYOUT_DIR / template).read_text(encoding="utf-8")
    tpl = tpl.replace("__BASE_CSS__", css)
    tpl = tpl.replace("__BODY_CLASS__", "transparent" if transparent else "")
    tpl = tpl.replace("--pad:76px;", f"--pad:76px; --overlay:{fields.pop('OVERLAY', '0')};")
    for k, v in fields.items():
        tpl = tpl.replace(f"__{k}__", v)
    tpl = brandmark.apply(tpl)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = LAYOUT_DIR / f".render_{out.stem}.html"
    tmp.write_text(tpl, encoding="utf-8")
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=["--font-render-hinting=none"])
            pg = b.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            pg.goto(tmp.as_uri())
            pg.wait_for_function("document.body.dataset.ready === '1'")
            pg.wait_for_timeout(80)
            pg.locator("#card").screenshot(path=str(out), omit_background=transparent)
            b.close()
    finally:
        tmp.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------------------


def render_roadmap(period: str, period_label: str, phases: list[dict],
                   date_str: str = "", segments: int | None = None,
                   transparent: bool = False, out: str | Path = "roadmap.png") -> Path:
    """phases: [{"text": str, "status": "done"|"now"|"next"}] — 3〜5件が読みやすい。

    The segment bar is derived from the phases rather than passed separately,
    so the bar and the list can never disagree about how far along things are.
    """
    n = segments or len(phases)
    segs = []
    for i in range(n):
        st = phases[i]["status"] if i < len(phases) else "next"
        segs.append(f'<i class="{st if st in ("done", "now") else ""}"></i>')

    rows = "".join(
        f'<div class="phase {p["status"]}">'
        f'<div class="st">{STATUS_LABEL.get(p["status"], "")}</div>'
        f'<div class="tx">{html.escape(p["text"])}</div></div>'
        for p in phases
    )
    return _shoot("roadmap.html", {
        "PERIOD": html.escape(period),
        "PERIOD_LABEL": html.escape(period_label),
        "SEGMENTS": "".join(segs),
        "PHASES": rows,
        "DATE": html.escape(_fmt_date(date_str)),
    }, Path(out), transparent)


def render_changelog(version: str, items: list[dict], when: str = "",
                     date_str: str = "", transparent: bool = False,
                     out: str | Path = "changelog.png") -> Path:
    """items: [{"tag": "NEW"|"IMP"|"FIX", "text": str}] — 3〜6件。"""
    rows = "".join(
        f'<div class="row {"fix" if it.get("tag") == "FIX" else ""}">'
        f'<div class="stamp"><span>{html.escape(it.get("tag", "IMP"))}</span></div>'
        f'<div class="tx">{html.escape(it["text"])}</div></div>'
        for it in items
    )
    return _shoot("changelog.html", {
        "VERSION": html.escape(version),
        "WHEN": html.escape(when),
        "COUNT": f"{len(items)}件の改善",
        "ROWS": rows,
        "DATE": html.escape(_fmt_date(date_str)),
    }, Path(out), transparent)


def render_feature(name_en: str, name_ja: str, lead: str, points: list[str],
                   date_str: str = "", transparent: bool = False,
                   out: str | Path = "feature.png") -> Path:
    """points: 最大3件。4件以上は1枚に収めず分けたほうが伝わる。"""
    pts = "".join(
        f'<div class="pt"><div class="n">{i}</div>'
        f'<div class="tx">{html.escape(t)}</div></div>'
        for i, t in enumerate(points[:3], 1)
    )
    return _shoot("feature.html", {
        "NAME_EN": html.escape(name_en),
        "NAME_JA": html.escape(name_ja),
        "LEAD": html.escape(lead),
        "POINTS": pts,
        "DATE": html.escape(_fmt_date(date_str)),
    }, Path(out), transparent)


def render_events(month: int, events: list[dict], area: str = "",
                  date_str: str = "", transparent: bool = False,
                  out: str | Path = "events.png") -> Path:
    """events: [{"day": "23", "wd": "SUN", "name": str, "place": str}] — 最大6件。"""
    rows = "".join(
        f'<div class="ev"><div class="d">{html.escape(e["day"])}'
        f'<small>{html.escape(e.get("wd", ""))}</small></div>'
        f'<div class="info"><div class="nm">{html.escape(e["name"])}</div>'
        f'<div class="pl">{html.escape(e.get("place", ""))}</div></div></div>'
        for e in events[:6]
    )
    return _shoot("events.html", {
        "MONTH": f"{month:02d}",
        "MONTH_EN": MONTH_EN[month - 1],
        "AREA": html.escape(area),
        "EVENTS": rows,
        "DATE": html.escape(_fmt_date(date_str or date.today().isoformat())),
    }, Path(out), transparent)


# --- covers -----------------------------------------------------------------
# Page one of a carousel. Different job from the interior pages: carry one fact
# and one instruction, and let the photograph do the rest.


def render_cover_events(month: int, count: int, area: str, photo: str | Path,
                        title: str = "今月のカーイベント", year: int | None = None,
                        overlay: float = 0.30, date_str: str = "",
                        transparent: bool = False,
                        out: str | Path = "cover_events.png") -> Path:
    tpl = _shoot("cover_events.html", {
        "PHOTO": _photo_html(photo),
        "MONTH": f"{month:02d}",
        "MONTH_EN": MONTH_EN[month - 1],
        "YEAR": str(year or date.today().year),
        "TITLE": html.escape(title),
        "COUNT": str(count),
        "AREA": html.escape(area),
        "DATE": html.escape(_fmt_date(date_str or date.today().isoformat())),
        "OVERLAY": str(overlay),
    }, Path(out), transparent)
    return tpl


def render_cover_feature(name_en: str, name_ja: str, hook: str, photo: str | Path,
                         kicker: str = "新機能", overlay: float = 0.30,
                         date_str: str = "", transparent: bool = False,
                         out: str | Path = "cover_feature.png") -> Path:
    return _shoot("cover_feature.html", {
        "PHOTO": _photo_html(photo),
        "KICKER": html.escape(kicker),
        "NAME_EN": html.escape(name_en),
        "NAME_JA": html.escape(name_ja),
        "HOOK": html.escape(hook),
        "DATE": html.escape(_fmt_date(date_str or date.today().isoformat())),
        "OVERLAY": str(overlay),
    }, Path(out), transparent)
