"""REVO news pipeline configuration."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sources
#
# Verify each feed URL by hand before enabling it — feed paths change and a
# silently dead feed looks identical to a quiet news day. `weight` nudges the
# score for outlets whose readership overlaps REVO's most closely.
# ---------------------------------------------------------------------------
SOURCES = [
    {"name": "Auto Messe Web", "url": "https://www.automesseweb.jp/feed", "weight": 1.2},
    {"name": "WEB CARTOP", "url": "https://www.webcartop.jp/feed", "weight": 1.1},
    {"name": "Motor Fan", "url": "https://motor-fan.jp/feed", "weight": 1.0},
    {"name": "Car Watch", "url": "https://car.watch.impress.co.jp/data/rss/1.0/cw/feed.rdf", "weight": 1.0},
    {"name": "Response", "url": "https://response.jp/rss/index.rdf", "weight": 0.9},
    {"name": "Creative Trend", "url": "https://creative311.com/feed", "weight": 1.0},
    {"name": "オンラインオートサロン", "url": "https://www.tokyoautosalon.jp/rss", "weight": 1.1},
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
