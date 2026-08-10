# -*- coding: utf-8 -*-
"""
scrape_events_wcc.py

WCC(World Coffee Championships、wcc.coffee)のシーズン開催情報を取得する。
7つの世界大会(World Barista/Brewers Cup/Latte Art/Coffee in Good Spirits/
Cup Tasters/Coffee Roasting/Cezve-Ibrik Championship)を統括する団体。

【設計上の判断】wcc.coffeeはSquarespaceの「Fluid Engine」で構築されており、
各要素のクラス名がハッシュ値(例: fe-block-e8532a856146843e7672)で管理されて
いる。これはページ編集のたびに変わりうるため、CSS要素を細かく狙うセレクタは
壊れやすい。そのため、ページ全体のテキストから「都市名 World Coffee
Championships」「日程」「会場」「チャンピオン発表」という決まった文言パターンを
正規表現で拾う方式を採用する。

robots.txt確認済み(2026年8月時点): /search, /account, /api/ 等は制限されるが、
トップページ・ニュースページ等の一般コンテンツは対象外。Squarespace標準の
robots.txtで、主要AIボット(GPTBot, ClaudeBot等)は個別にAllow指定あり。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "WCC(World Coffee Championships)",
    "url": "https://wcc.coffee/",
    "robots_txt_status": "許可(2026-08確認。/search, /account, /api/等のみ制限)",
    "update_cadence": "月次",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「都市名 World Coffee Championships  日程  at [会場名](URL)」パターン
EVENT_PATTERN = re.compile(
    r"###\s+(?P<title>.+?World Coffee Championships)\s+"
    r"(?P<date_range>[A-Za-z]+\s+\d{1,2}(?:-\d{1,2})?,?\s*\d{4})\s+"
    r"at\s+\[(?P<venue>[^\]]+)\]\((?P<venue_url>[^)]+)\)",
    re.MULTILINE,
)

# 「Champion: [チャンピオン名, representing the Competition Body of 国名]」パターン
# (開催後のみ出現。シーズン中の未開催イベントには付かない)
CHAMPION_PATTERN = re.compile(r"Champion:\s+\[([^\]]+)\]")

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def fetch_page_text(url: str) -> str:
    """ページを取得し、Squarespaceの複雑なグリッド構造を無視して
    テキストのみを抽出する(細かいCSS構造に依存しないための設計判断)。"""
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with(" ")
    # 見出し要素はMarkdownの "### " 相当に変換しておく(正規表現パターンとの整合のため)
    for h in soup.find_all(["h1", "h2", "h3"]):
        h.insert_before("\n### ")
    return soup.get_text()


def parse_date_range(date_range: str, host_country_hint: str = None):
    """「October 22-25, 2026」のような文字列をstart_date/end_dateに変換する。"""
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})(?:-(\d{1,2}))?,?\s*(\d{4})", date_range)
    if not m:
        return None, None
    month_name, day_start, day_end, year = m.groups()
    month = MONTH_MAP.get(month_name)
    if not month:
        return None, None
    start_date = f"{year}-{month:02d}-{int(day_start):02d}"
    end_date = f"{year}-{month:02d}-{int(day_end):02d}" if day_end else start_date
    return start_date, end_date


def scrape_season_events() -> list[dict]:
    """トップページの「シーズンイベント」セクションから開催都市・日程・会場・
    (開催済みの場合)チャンピオン情報を抽出する。"""
    text = fetch_page_text(EVENT_SOURCE_INFO["url"])

    records = []
    matches = list(EVENT_PATTERN.finditer(text))
    for i, m in enumerate(matches):
        start_date, end_date = parse_date_range(m.group("date_range"))

        # このイベント記述の直後(次のイベント見出しまでの間)にチャンピオン発表が
        # あれば拾う。無ければ「開催前」のイベントと判断する。
        segment_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[m.end():segment_end]
        champion_match = CHAMPION_PATTERN.search(segment)

        records.append({
            "event_source": EVENT_SOURCE_INFO["name"],
            "name": m.group("title").strip(),
            "event_type": "competition",
            "venue": m.group("venue").strip(),
            "venue_url": m.group("venue_url").strip(),
            "start_date": start_date,
            "end_date": end_date,
            "champion": champion_match.group(1).strip() if champion_match else None,
            "source_url": EVENT_SOURCE_INFO["url"],
        })

    return records


if __name__ == "__main__":
    import json
    events = scrape_season_events()
    output = {"event_source": EVENT_SOURCE_INFO, "events": events}
    with open("data_events_wcc.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(events)}件を data_events_wcc.json に出力しました")
