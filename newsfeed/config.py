"""REVO news pipeline configuration."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sources
#
# Verify each feed URL by hand before enabling it — feed paths change and a
# silently dead feed looks identical to a quiet news day. `weight` nudges the
# score for outlets whose readership overlaps REVO's most closely.
# ---------------------------------------------------------------------------
# 2026-08-18 実測でフィードを検証。以下は記事フィードを提供していないか
# 到達できなかったため外した:
#   Motor Fan            /feed も /rss もタグ一覧を返す（記事フィードなし）
#   Car Watch            403（UA弾き）
#   Creative Trend       未到達
#   オンラインオートサロン  未到達
#   Response             フィードは生きているが業界紙。50件中45件が人事情報・
#                        建設機械・蓄電池・物流など。読者層と一致しない
# 生きている2本だけで日次30件前後。まずはこの規模で運用する。
SOURCES = [
    {"name": "Auto Messe Web", "url": "https://www.automesseweb.jp/feed", "weight": 1.2},
    {"name": "WEB CARTOP", "url": "https://www.webcartop.jp/feed", "weight": 1.1},
]

# ---------------------------------------------------------------------------
# Mechanical exclusion
#
# Runs before the model sees anything. Two reasons this layer exists at all:
# a fatal-accident or recall headline reaching the account is unrecoverable
# reputational damage, and paying to score obvious junk is waste.
# ---------------------------------------------------------------------------
EXCLUDE = {
    # Never publishable. A single one of these getting through costs the
    # account its credibility, so they are dropped before scoring.
    "harm": [
        "死亡", "死者", "亡くな", "遺体", "重体", "重傷", "多重事故", "衝突事故",
        "ひき逃げ", "当て逃げ", "飲酒運転", "あおり運転", "逮捕", "起訴", "書類送検",
        "容疑", "詐欺", "盗難", "窃盗", "殺人", "炎上事故", "火災",
    ],
    # Recalls and defect notices invite complaint threads and read as a
    # consumer-advocacy account, which REVO is not.
    "defect": ["リコール", "改善対策", "不具合", "欠陥", "無償修理", "使用停止", "適合の除外"],
    # Outside the readership: policy, commercial vehicles, industry numbers.
    "offtopic": [
        "補助金", "税制", "法改正", "規制強化", "carbon", "カーボンニュートラル",
        "販売台数", "生産台数", "決算", "業績", "株価", "出資", "提携交渉",
        # NOTE: a bare "トラック" also matches ピックアップトラック, which is
        # exactly the kind of import news this readership does care about.
        # Keep commercial-vehicle terms specific.
        "商用車", "軽トラ", "商用バン", "ハイエース", "N-VAN", "サンバー", "キャリイ",
        "自動運転", "ライドシェア", "MaaS", "充電インフラ",
        # 実フィードで通過してしまったもの
        "〈PR〉", "［PR］", "【PR】",
        "車庫証明", "ながら運転", "違反", "免許", "交通ルール", "取り締まり",
        "電動バイク", "二輪", "バイク",
        "下請け", "サプライヤー",
        "食堂", "グルメ", "ラーメン", "定食",
    ],
}

# Overseas news is published, not excluded — it is simply marked so the reader
# can see at a glance that a story is not about the domestic market. Relevance
# is the scoring layer's call, not a keyword's.
FOREIGN_MARKET = [
    "北米市場向け", "北米向け", "インド", "中国市場", "欧州市場向け", "豪州",
    "米国", "アメリカ", "欧州", "ドイツ", "英国", "海外", "ワールドプレミア",
]

# ---------------------------------------------------------------------------
# Hard limits
#
# The previous Autopilot drifted because bot output had no ceiling. These are
# constants, not settings: the pipeline must not be able to talk itself into
# a busier day.
# ---------------------------------------------------------------------------
MAX_CANDIDATES_PER_DAY = 8      # how many the model may put in front of a human
SCORE_THRESHOLD = 6             # below this, not worth a human glance

# There is no per-day or per-week posting cap. The ceiling that remains is on
# how many candidates are put in front of a human each day — a review list
# longer than this stops being read, which is the failure mode that matters.
# Discord number reactions run out at 10, so 8 leaves headroom.

# Publishing windows, JST, keyed by date.isoweekday() — Monday is 1.
# The digest runs every day; weekend slots sit later because weekend mornings
# belong to users heading out, not to reading news.
POST_WINDOWS = {
    1: ["19:00"], 2: ["19:00"], 3: ["19:00"], 4: ["19:00"], 5: ["19:00"],
    6: ["21:00"], 7: ["21:00"],
}

CATEGORIES = ["DEBUT", "PARTS", "EVENT", "RACE", "RETRO"]
HEADLINE_MAX_CHARS = 34         # measured limit of the card renderer
