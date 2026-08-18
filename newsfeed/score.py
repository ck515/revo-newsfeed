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
- 全角{HEADLINE_MAX_CHARS}文字以内。超えるとカード上で文字が小さくなり読めません
- 元記事の見出しをそのまま使わず、要点だけを平叙で書く
- 煽り表現、体言止めの多用、「！」「衝撃」「驚愕」は使わない
- 走行タイムや速度を主語にしない（アプリ側の制約と整合させるため）

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
    if text.rstrip().endswith(("," , '"')) or text.count("[") > text.count("]"):
        raise ValueError(
            "モデルの出力が途中で切れています。max_tokens が不足しています。"
            f"（出力 {len(text)} 文字）"
        )
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    return data


def score_via_api(items: list[dict]) -> list[dict]:
    """Score a batch with the Anthropic API. Needs ANTHROPIC_API_KEY."""
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic()
    # Roughly 130 tokens per scored item; the cap has to scale with the batch
    # or the JSON array is truncated mid-string and fails to parse.
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


def validate(scored: list[dict]) -> list[str]:
    """Check the model obeyed the output contract. Returns a list of problems."""
    problems = []
    for s in scored:
        sid = s.get("id", "?")
        cat, sc = s.get("category"), s.get("score")
        if cat is None:
            # only allowed for stories that will never be posted anyway
            if isinstance(sc, int) and sc >= SCORE_THRESHOLD:
                problems.append(f"{sid}: category が null なのに score {sc}")
        elif cat not in CATEGORIES:
            problems.append(f"{sid}: 未知のカテゴリ {cat!r}")
        h = s.get("headline") or ""
        if len(h) > HEADLINE_MAX_CHARS:
            problems.append(f"{sid}: 見出し{len(h)}字（上限{HEADLINE_MAX_CHARS}）")
        # A headline is only needed for stories that can actually be posted.
        if not h and isinstance(sc, int) and sc >= SCORE_THRESHOLD:
            problems.append(f"{sid}: 見出しが空なのに score {sc}")
        if s.get("region") not in ("JP", "WORLD", None):
            problems.append(f"{sid}: 不正な region {s.get('region')!r}")
        if len(s.get("keywords", [])) > 3:
            problems.append(f"{sid}: キーワード{len(s['keywords'])}件（上限3）")
        if not isinstance(s.get("score"), int) or not 0 <= s["score"] <= 10:
            problems.append(f"{sid}: 不正なスコア {s.get('score')!r}")
    return problems
