# -*- coding: utf-8 -*-
"""
scrape_events_wcc.py

WCC(World Coffee Championships、wcc.coffee)のシーズン開催情報を取得する。
7つの世界大会(World Barista/Brewers Cup/Latte Art/Coffee in Good Spirits/
Cup Tasters/Coffee Roasting/Cezve-Ibrik Championship)を統括する団体。

【不具合修正の経緯(2026-08)】
本スクリプトは当初、ページ全体のテキストから「### 都市名 World Coffee
Championships 日程 at [会場名](URL)」というMarkdown風のパターンを正規表現で
拾う設計だった。しかしこれはBeautifulSoupのget_text()が実際に返す出力を
正しく想定していなかった不具合で、実データを確認したところ会場名は
`at <a href="...">会場名</a>` というHTMLリンクとして書かれており、
get_text()はリンクをMarkdownの`[会場名](URL)`形式には変換しない
(単なる「at 会場名」という平文になる)。そのためEVENT_PATTERNは実際の
ページに対して一度もマッチしない状態だった。scrape-events.ymlが今回
初めて実行されるまでこの不具合は発覚せず、当初手動でシードされていた
WCCイベント2件が、本スクリプトが返す空の結果で上書き・commitされてしまう
事故につながった。

【修正後の設計】実データ確認済み(2026-08時点、シーズン中の5大会すべてで
同一構造を確認): 各大会は`<h1>/<h2>/<h3>`のいずれか1つの見出し要素内に、
「都市名 World Coffee Championships」「日程」「at 会場名(<a>タグ)」が
<br>区切りで収まっている。Markdownパターンへの正規表現ではなく、この
見出し要素をDOM単位で処理する方式に変更した。会場名がBangkok開催のように
複数の<a>タグ(例:「World of Coffee 」+「Bangkok」)に分かれて書かれている
実データも確認済みのため、見出し内の<a>タグをすべて連結して会場名とする。

チャンピオン発表(開催済み大会の優勝者)についても、実データ確認時点では
このページ上に該当する記述が見当たらなかった(未着手のシーズンのみ掲載されて
いる可能性がある)。見つかった場合に備えてCHAMPION_PATTERNは維持するが、
旧実装と同じMarkdown前提の誤りがあったため、平文の「Champion: 名前」を
直接拾う形に修正している。

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

TITLE_MARKER = "World Coffee Championships"
DATE_RANGE_PATTERN = re.compile(r"([A-Za-z]+)\s+(\d{1,2})(?:-(\d{1,2}))?,?\s*(\d{4})")

# 「Champion: 名前」パターン(開催後のみ出現想定。実データではまだ確認できて
# いないが、将来ページに追加された場合に備えて残す)
CHAMPION_PATTERN = re.compile(r"Champion:\s*([^\n]+)")

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_date_range(date_text: str):
    """「October 22-25, 2026」のような文字列をstart_date/end_dateに変換する。"""
    m = DATE_RANGE_PATTERN.search(date_text)
    if not m:
        return None, None
    month_name, day_start, day_end, year = m.groups()
    month = MONTH_MAP.get(month_name)
    if not month:
        return None, None
    start_date = f"{year}-{month:02d}-{int(day_start):02d}"
    end_date = f"{year}-{month:02d}-{int(day_end):02d}" if day_end else start_date
    return start_date, end_date


def find_champion(heading) -> str | None:
    """見出し要素から次の見出しまでの兄弟要素のテキストから
    「Champion: 名前」を探す(開催済み大会のみ出現する想定)。"""
    for sib in heading.find_next_siblings():
        if getattr(sib, "name", None) in ("h1", "h2", "h3"):
            break
        text = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else ""
        m = CHAMPION_PATTERN.search(text)
        if m:
            return m.group(1).strip()
    return None


def scrape_season_events() -> list[dict]:
    """トップページの「シーズンイベント」セクションから開催都市・日程・会場・
    (開催済みの場合)チャンピオン情報を抽出する。"""
    soup = fetch_soup(EVENT_SOURCE_INFO["url"])

    records = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        heading_text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
        if TITLE_MARKER not in heading_text:
            continue

        date_match = DATE_RANGE_PATTERN.search(heading_text)
        if not date_match:
            # 「Welcome to the World Coffee Championships」のような、日程を
            # 伴わない見出し(セクションタイトル等)は対象外として読み飛ばす
            continue

        title = heading_text[:date_match.start()].strip()
        remainder = heading_text[date_match.end():].strip()
        venue = re.sub(r"^at\s+", "", remainder, flags=re.IGNORECASE).strip() or None

        venue_links = heading.find_all("a")
        venue_url = venue_links[0].get("href") if venue_links else None

        start_date, end_date = parse_date_range(heading_text)

        records.append({
            "event_source": EVENT_SOURCE_INFO["name"],
            "name": title,
            "event_type": "competition",
            "venue": venue,
            "venue_url": venue_url,
            "start_date": start_date,
            "end_date": end_date,
            "champion": find_champion(heading),
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
