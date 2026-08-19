"""Verify that model designations survived into the generated headline.

Asking the model not to shorten a car name is not enough — it still does, and a
headline naming the wrong car is worse than no post at all. So the headline is
checked against the source title: any designation present in the source and
missing or truncated in the headline is repaired mechanically.

The unit that matters is the designation *run*: "WRX S4", "GR86", "ZC33S",
"スイフトスポーツ". Losing any part of one names a different car.
"""

from __future__ import annotations

import re

# Latin+digit runs ("WRX S4", "ZC33S", "GR86", "911 GT3 RS") and katakana runs
# ("スイフトスポーツ"). Grade letters are joined to the token before them so
# "WRX S4" is treated as one unit rather than "WRX" plus a stray "S4".
_LATIN = r"[A-Za-z0-9][A-Za-z0-9\-]*"
_GRADE = r"(?:\s+(?:S4|STI|RS|GT[0-9R]*|Type\s?R|SV|SS|GTI|R|S|Z|X)\b)*"
# A katakana name may carry a Latin or numeric tail with no space:
# シビックタイプR, ランドクルーザー250. Splitting those apart was why
# "シビックタイプR" came back as "シビックタイプ".
_KATA = r"[ァ-ヶー]{2,}(?:[A-Za-z0-9][A-Za-z0-9\-]*)?"
TOKEN_RE = re.compile(rf"(?P<latin>{_LATIN}{_GRADE})|(?P<kata>{_KATA})")

# Words that look like designations but are not, so a missing one means nothing.
STOPWORDS = {
    "the", "and", "for", "new", "web", "pr", "ai", "ev", "suv", "mt", "at",
    "レポート", "ニュース", "インタビュー", "モデル", "グレード", "スペック",
    "デザイン", "エンジン", "システム", "ブランド", "メーカー", "シリーズ",
    "オーナー", "ユーザー", "サーキット", "パーツ", "カスタム", "チューニング",
    "スポーツカー", "ミーティング", "イベント",
}


def designations(text: str) -> list[str]:
    """Designation-like runs in a piece of text, longest first."""
    out = []
    for m in TOKEN_RE.finditer(text or ""):
        tok = m.group(0).strip()
        if len(tok) < 2 or tok.lower() in STOPWORDS:
            continue
        # A bare number is a year or a count far more often than a model.
        if tok.isdigit() and len(tok) != 2:
            continue
        out.append(tok)
    return sorted(set(out), key=len, reverse=True)


def _stub(source_tok: str, headline: str) -> str | None:
    """The shortened form of the name found in the headline, if any.

    Both ends are checked: a name can be cut from the back ("WRX S4" -> "WRX")
    or from the front ("GR86" -> "86"). Only checking prefixes missed the
    second case entirely.
    """
    if source_tok in headline:
        return None
    best = None
    for n in range(len(source_tok) - 1, 1, -1):
        for stub in (source_tok[:n].rstrip(" -"), source_tok[-n:].lstrip(" -")):
            if len(stub) >= 2 and stub in headline:
                if best is None or len(stub) > len(best):
                    best = stub
        if best:
            break
    return best


def check(headline: str, source_title: str) -> list[tuple[str, str]]:
    """Returns (shortened form found, full form expected) for each damaged name."""
    issues = []
    for tok in designations(source_title):
        stub = _stub(tok, headline)
        if stub:
            issues.append((stub, tok))
    # Keep only the outermost match per name so "WRX"→"WRX S4" is not also
    # reported as "WR"→"WRX S4".
    issues.sort(key=lambda p: len(p[0]), reverse=True)
    seen: list[tuple[str, str]] = []
    for stub, full in issues:
        if any(stub in s and full == f for s, f in seen):
            continue
        seen.append((stub, full))
    return seen


def fix(headline: str, source_title: str) -> tuple[str, list[str]]:
    """Restore any shortened designation. Returns (headline, notes)."""
    notes = []
    for stub, full in check(headline, source_title):
        # Replace the first standalone occurrence only; a name repeated in a
        # headline is rare and replacing every hit risks mangling other words.
        idx = headline.find(stub)
        if idx < 0:
            continue
        headline = headline[:idx] + full + headline[idx + len(stub):]
        notes.append(f"車名を復元: {stub} → {full}")
    return headline, notes
