"""Generate the post body for the cards a human actually picked.

Run at publish time, not at scoring time: only one to three items a day reach
this stage, so the model can be given the real article text and asked for
something worth reading, instead of writing thirty bodies that mostly get
thrown away.

The previous behaviour — slicing 120 characters off the feed summary — was
republishing the outlet's own sentences. Everything here is rewritten from the
facts, in REVO's voice.
"""

from __future__ import annotations

import os
import re

MODEL = "claude-sonnet-4-6"

SYSTEM = """あなたはREVOというアプリのSNS運用担当です。

REVOは首都圏の車好き向けの地図型コミュニティアプリで、Instagramのフォロワーは
JDM・旧車・カスタム・スポーツカー文化に関心のある個人オーナーです。

与えられたニュースについて、Instagramの投稿本文を書いてください。

書き方
- 120〜180字。読み切れる長さに収める
- 元記事の文章をそのまま使わない。事実だけ拾って自分の言葉で書く
- 事実に忠実に。記事に書かれていないスペックや価格を創作しない
- 車種名・グレード名・型式は元記事の表記を一字も変えずに使う。
  スイフトスポーツをスイフト、WRX S4をWRX のように縮めない。
  グレード記号（S / SV / RS / STI など）と型式（ZC33S、G87 など）は
  一文字違うと別の車を指すため、必ず原文どおりに残す
- 車好きが「へえ」と思う一点に絞る。全部を要約しようとしない
- 平叙で書く。「！」「衝撃」「驚愕」「必見」は使わない
- 断定できないことは「〜とみられる」「〜という」で書く
- 絵文字は使わない
- ハッシュタグは書かない（別で付ける）
- 最後の一文でフォロワーに小さく問いかけると反応が付きやすい。無理なら省略可

出力は本文だけ。見出しの繰り返し、前置き、説明は不要です。"""


def _client():
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic()


def _article_text(url: str, limit: int = 3000) -> str:
    """Pull readable text off the article page so the body is written from the
    facts rather than from a 120-character feed blurb."""
    import requests

    try:
        r = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; REVO-newsfeed/1.0)"},
        )
        r.raise_for_status()
        html = r.text
        html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", html)
        text = re.sub(r"&[a-z]+;", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:limit]
    except Exception as e:
        print(f"  記事本文の取得に失敗: {e}")
        return ""


def generate(item: dict, use_article: bool = True) -> str:
    """Return the post body, or "" if generation is not possible."""
    facts = [
        f"見出し: {item.get('headline', '')}",
        f"元タイトル: {item.get('title', '')}",
        f"媒体: {item.get('source', '')}",
        f"カテゴリ: {item.get('category', '')}",
    ]
    summary = (item.get("summary") or "").strip()
    if summary:
        facts.append(f"要約: {summary[:400]}")
    if use_article and item.get("url"):
        body = _article_text(item["url"])
        if body:
            facts.append(f"記事本文（抜粋）: {body}")

    try:
        resp = _client().messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM,
            messages=[{"role": "user", "content": "\n".join(facts)}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print(f"  本文の生成に失敗: {e}")
        return ""

    # The model occasionally opens by restating the headline; drop that line.
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines and lines[0] == item.get("headline", "").strip():
        lines = lines[1:]
    body = "\n".join(lines).strip()

    # Same shortening happens in the body as in the headline, so the same
    # repair applies.
    import modelnames

    src = " ".join(filter(None, [item.get("title"), item.get("summary")]))
    if src.strip() and body:
        body, changes = modelnames.fix(body, src)
        for c in changes:
            print(f"  本文の{c}")
    return body
