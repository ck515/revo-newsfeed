"""Scoring stage — asks the model which stories are worth a human glance.

The job here is mostly rejection. Twenty items in, three out. The prompt is
written so the model has to justify a high score against a named readership
rather than rate "newsworthiness" in the abstract.
"""

from __future__ import annotations

import json
import os
import re

from config import CATEGORIES, HEADLINE_MAX_CHARS, SCORE_THRESHOLD

MODEL = "claude-sonnet-4-6"

SYSTEM = f"""あなたはREVOというアプリのSNS運用担当です。

REVOは首都圏の車好き向けの地図型コミュニティアプリで、Instagramのフォロワーは
JDM・旧車・カスタム・スポーツカー文化に関心のある個人オーナーです。
法人向けでも、業界関係者向けでもありません。

与えられた記事に0〜10点を付けてください。基準は「この読者が反応するか」だけです。
記事の重要性ではありません。

高得点（8〜10）
- スポーツカー・ホットハッチの新型/改良/復活
- 有名チューニングメーカーの新製品
- 大型オフ会・走行会・カスタムイベントの開催情報
- 旧車・絶版車の相場や再評価

中得点（5〜7）
- 一般車の改良で、走りに関わる変更があるもの
- 海外スポーツカーの発表で国内導入が見込めるもの
- 国内モータースポーツの節目

低得点（0〜4）
- SUV・ミニバン・軽の実用面の話
- 業界動向、統計、政策
- 車と無関係な記事

海外ニュースも対象です。国内導入の見込みや車種の知名度で判断してください。
スーパーカー、欧州のホットハッチ、海外のカスタム動向は国内の読者も見ています。
一方、他市場専用の実用車（インド専用SUVなど）は低得点です。

region は日本国内の話なら "JP"、海外の話なら "WORLD" にしてください。

カテゴリは次から1つだけ選びます: {", ".join(CATEGORIES)}
どれにも当てはまらない記事は score を4以下にし、category は null にしてください。
汎用カテゴリはありません。

headline はカード画像に載る見出しです。
- 全角30文字以内。上限は{HEADLINE_MAX_CHARS}文字だが、余裕を持って30以内に収めること
- 元記事の見出しをそのまま使わず、要点だけを平叙で書く
- 煽り表現、体言止めの多用、「！」「衝撃」「驚愕」は使わない
- 走行タイムや速度を主語にしない（アプリ側の制約と整合させるため）

**車種名・グレード名・型式は元記事の表記を一字も変えずに使ってください。**
これは短縮の対象外です。字数に収まらない場合は、車名ではなく他の語を削ってください。
この読者にとって型式やグレードは記事の中身そのものであり、一文字違うと別の車を
指すことになります。

  誤: スイフトスポーツ → スイフト
  誤: シビックタイプR → シビック
  誤: GR86 → 86
  誤: ランドクルーザー250 → ランドクルーザー
  誤: ZC33S → ZC33
  誤: WRX S4 → WRX

グレードの記号（S / SV / RS / GT / Type R / STI など）、型式（ZC33S、GDB、
G87 など）、世代を示す数字（86、250、911 など）は、すべて記事の表記どおりに
残してください。読者はここで車を特定しています。

必ずJSON配列のみを返してください。前置き、説明、コードフェンスは不要です。
各要素の形式:
{{"id": "<入力のid>", "score": <0-10>, "reason": "<20字程度の判断理由>",
  "category": "<{'|'.join(CATEGORIES)}>", "headline": "<{HEADLINE_MAX_CHARS}字以内>",
  "keywords": ["<最大3件、#なし>"], "region": "<JP|WORLD>",
  "video_official": <true|false>}}

video_official は、記事にメーカー公式またはパーツメーカー公式の動画が
埋め込まれている場合のみ true にしてください。判断できない場合は false です。"""


def build_user_message(items: list[dict]) -> str:
    payload = [
        {
            "id": i["id"],
            "source": i.get("source", ""),
            "title": i.get("title", ""),
            "summary": (i.get("summary") or "")[:300],
            "has_video": bool(i.get("has_video")),
        }
        for i in items
    ]
    return json.dumps(payload, ensure_ascii=False, indent=1)


def _parse(text: str) -> list[dict]:
    """Strip fences and parse. Raises on malformed output rather than guessing."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Truncated output: salvage the objects that did close. Losing the tail
        # of a batch beats losing the whole day.
        salvaged, depth, start = [], 0, None
        for i, ch in enumerate(cleaned):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        salvaged.append(json.loads(cleaned[start : i + 1]))
                    except json.JSONDecodeError:
                        pass
        if not salvaged:
            raise
        print(f"  ! 出力が途中で切れました。{len(salvaged)}件を救出します"
              f"（max_tokens 不足の可能性）")
        return salvaged
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    return data


def score_via_api(items: list[dict]) -> list[dict]:
    """Score a batch with the Anthropic API. Needs ANTHROPIC_API_KEY."""
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic()
    # Roughly 130 tokens per scored item. A fixed cap truncates the JSON array
    # mid-string once the batch grows, so it has to scale with the batch.
    resp = client.messages.create(
        model=MODEL,
        max_tokens=min(16000, 1000 + 160 * len(items)),
        system=SYSTEM,
        messages=[{"role": "user", "content": build_user_message(items)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _parse(text)


def score_from_file(path: str) -> list[dict]:
    """Load scores produced elsewhere — used to test the pipeline without a key."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge(items: list[dict], scores: list[dict]) -> list[dict]:
    """Join scores onto items, newest-highest first, dropping anything unscored."""
    by_id = {s["id"]: s for s in scores}
    out = []
    for it in items:
        s = by_id.get(it["id"])
        if not s:
            continue
        out.append({**it, **s})
    return sorted(out, key=lambda x: x["score"], reverse=True)


def above_threshold(scored: list[dict]) -> list[dict]:
    return [s for s in scored if s["score"] >= SCORE_THRESHOLD]


def repair(scored: list[dict]) -> list[str]:
    """Fix contract violations in place and return what was changed.

    Aborting the run on a violation was the wrong trade: two soft problems in a
    batch of sixteen threw away the entire day's news and the account went
    silent with no explanation. None of these violations are fatal to the item
    they affect, let alone to the batch — so each is repaired, the repair is
    reported, and the run continues.
    """
    notes = []
    for s_ in scored:
        sid = s_.get("id", "?")

        # A headline over the limit renders smaller, not broken. Trim it at a
        # punctuation boundary so it still reads as a sentence.
        h = s_.get("headline") or ""
        if len(h) > HEADLINE_MAX_CHARS:
            # Trim only at a punctuation boundary, and only if nothing
            # alphanumeric is lost. Model designations live in those runs —
            # "WRX S4" cut to "WRX", or "ZC33S" to "ZC33", names a different
            # car. An over-long headline merely renders a size smaller; a
            # wrong one is wrong on the feed forever, so the trim is skipped
            # rather than allowed to damage a name.
            cut = None
            for mark in ("、", "。", "，"):
                i = h.rfind(mark, 0, HEADLINE_MAX_CHARS + 1)
                if i >= HEADLINE_MAX_CHARS - 14:
                    cand = h[:i]
                    if not any(ch.isalnum() for ch in h[i:]):
                        cut = cand
                    break
            if cut:
                s_["headline"] = cut.rstrip("、。， ")
                notes.append(f"{sid}: 見出しを{len(h)}字→{len(s_['headline'])}字に短縮")
            else:
                notes.append(
                    f"{sid}: 見出しが{len(h)}字（上限{HEADLINE_MAX_CHARS}）。"
                    f"車名を壊さないため短縮せず、文字を小さくして出します"
                )

        # An unknown or missing category cannot be rendered, and a story that
        # fits none of the five was not worth offering anyway — so demote it
        # instead of dropping the batch.
        cat, sc = s_.get("category"), s_.get("score")
        if cat is not None and cat not in CATEGORIES:
            notes.append(f"{sid}: 未知のカテゴリ {cat!r} → 対象外にしました")
            s_["score"] = min(sc if isinstance(sc, int) else 0, SCORE_THRESHOLD - 1)
        elif cat is None and isinstance(sc, int) and sc >= SCORE_THRESHOLD:
            notes.append(f"{sid}: category が null のため対象外にしました（score {sc}）")
            s_["score"] = SCORE_THRESHOLD - 1

        if not (s_.get("headline") or "").strip() and \
                isinstance(s_.get("score"), int) and s_["score"] >= SCORE_THRESHOLD:
            notes.append(f"{sid}: 見出しが空のため対象外にしました")
            s_["score"] = SCORE_THRESHOLD - 1

        if len(s_.get("keywords", [])) > 3:
            n = len(s_["keywords"])
            s_["keywords"] = s_["keywords"][:3]
            notes.append(f"{sid}: キーワードを{n}件→3件に切り詰め")

        if not isinstance(s_.get("score"), int) or not 0 <= s_["score"] <= 10:
            notes.append(f"{sid}: 不正なスコア {s_.get('score')!r} → 対象外にしました")
            s_["score"] = 0

        if s_.get("region") not in ("JP", "WORLD", None):
            s_["region"] = None

    return notes


def validate(scored: list[dict]) -> list[str]:
    """Check the model obeyed the output contract. Returns a list of problems."""
    problems = []
    for s in scored:
        sid = s.get("id", "?")
        # Only items that can still be posted matter. Anything repair() pushed
        # below the threshold is already out of the running, and flagging it
        # again would make a handled problem look unhandled.
        if isinstance(s.get("score"), int) and s["score"] < SCORE_THRESHOLD:
            continue
        cat, sc = s.get("category"), s.get("score")
        if cat is None:
            # only allowed for stories that will never be posted anyway
            if isinstance(sc, int) and sc >= SCORE_THRESHOLD:
                problems.append(f"{sid}: category が null なのに score {sc}")
        elif cat not in CATEGORIES:
            problems.append(f"{sid}: 未知のカテゴリ {cat!r}")
        # Length is not checked here. repair() deliberately leaves a headline
        # long when trimming it would damage a model name, and the renderer
        # handles the overflow by stepping the type down. Reporting it as a
        # violation would make --strict abort on a decision that was correct.
        h = s.get("headline") or ""
        if not h and isinstance(sc, int) and sc >= SCORE_THRESHOLD:
            problems.append(f"{sid}: 見出しが空なのに score {sc}")
        if s.get("region") not in ("JP", "WORLD", None):
            problems.append(f"{sid}: 不正な region {s.get('region')!r}")
        if len(s.get("keywords", [])) > 3:
            problems.append(f"{sid}: キーワード{len(s['keywords'])}件（上限3）")
        if not isinstance(s.get("score"), int) or not 0 <= s["score"] <= 10:
            problems.append(f"{sid}: 不正なスコア {s.get('score')!r}")
    return problems
