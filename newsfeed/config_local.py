"""Local settings. Copy to config_local.py — that filename is never shipped,
so these survive unzipping a new version of the pipeline over the top.

Values here replace the ones in config.py entirely (they are not merged), so
copy the whole list you want, not just the part you are changing.
"""

# Feeds verified against real traffic on 2026-08-18. The ones removed:
#   Motor Fan            /feed and /rss both return a tag list, not articles
#   Car Watch            403
#   Creative Trend       unreachable
#   オンラインオートサロン  unreachable
#   Response             live, but a trade paper — 45 of 50 items were HR
#                        notices, construction machinery, batteries, logistics
SOURCES = [
    {"name": "Auto Messe Web", "url": "https://www.automesseweb.jp/feed", "weight": 1.2},
    {"name": "WEB CARTOP", "url": "https://www.webcartop.jp/feed", "weight": 1.1},
]

EXCLUDE = {
    "harm": [
        "死亡", "死者", "亡くな", "遺体", "重体", "重傷", "多重事故", "衝突事故",
        "ひき逃げ", "当て逃げ", "飲酒運転", "あおり運転", "逮捕", "起訴", "書類送検",
        "容疑", "詐欺", "盗難", "窃盗", "殺人", "炎上事故", "火災",
    ],
    "defect": ["リコール", "改善対策", "不具合", "欠陥", "無償修理", "使用停止", "適合の除外"],
    "offtopic": [
        "補助金", "税制", "法改正", "規制強化", "カーボンニュートラル",
        "販売台数", "生産台数", "決算", "業績", "株価", "出資", "提携交渉",
        "商用車", "軽トラ", "商用バン", "ハイエース", "N-VAN", "サンバー", "キャリイ",
        "自動運転", "ライドシェア", "MaaS", "充電インフラ",
        # added after seeing what actually came through the live feeds
        "〈PR〉", "［PR］", "【PR】",
        "車庫証明", "ながら運転", "違反", "免許", "交通ルール", "取り締まり",
        "電動バイク", "二輪", "バイク",
        "下請け", "サプライヤー",
        "食堂", "グルメ", "ラーメン", "定食",
    ],
}

# none / category / article
CARD_BACKGROUND = "none"
