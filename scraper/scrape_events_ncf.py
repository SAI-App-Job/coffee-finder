# -*- coding: utf-8 -*-
"""
scrape_events_ncf.py

NAGOYA COFFEE FES.(nagoyacoffeefes.com)が運営する3つのブランドイベント
「NAGOYA COFFEE FESTIVAL」「HOSHIGAOKA COFFEE MARKET」「COFFEE JAM」の
開催情報を取得する。ユーザー指示により、この3つはそれぞれ個別のイベントとして
扱う。

【サイト構造】実データ確認済み(2026-08時点): Shopify製。専用のスケジュール
ページは無く(ナビゲーションはTOPのみ)、トップページの「PROJECTs」セクションに
3ブランド全ての過去〜現在の開催回が`.banner__box`(スライドショー用バナー)として
連続して並ぶ。各`.banner__box`は`.banner__heading`(イベント名 @ 会場)と
`.banner__text`(日程、または開催済みの場合は代わりに「LOOK BACK配信中」という
Instagram誘導文)を持つ。日程が明示されているのは次回開催が確定している
ブランドのみで、開催済みの回は日程情報がLOOK BACK案内に置き換わるため、
本スクレイパーは「日程が読み取れたイベントのみ」を取得対象とする
(TCF/SCAJスクレイパーと同じ「現在/次回のみ」設計)。

日程の書式は2パターン確認済み: トップの告知バナーでは見出し文の先頭に
「2026/9/19(Sat)-20(Sun) イベント名 @ 会場 開催!!」のように日程が英語曜日
付きで埋め込まれ、PROJECTsセクション内の各バナーでは`.banner__text`に
「2026/10/31(土)-11/1(日)」のように日本語曜日付きの日程が独立した段落として
入る。DATE_RANGE_PATTERNは曜日部分を`\([^)]*\)`として言語を問わず吸収する。

robots.txt確認済み(2026-08時点): Shopify標準構成。「User-agent: * / Allow: /」
で一般ページ(products/collections/pages/blogs)は許可、admin/cart/checkout/
account等の非公開・トランザクション系のみ制限。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "NAGOYA COFFEE FES.(NAGOYA COFFEE FESTIVAL / HOSHIGAOKA COFFEE MARKET / COFFEE JAM)",
    "url": "https://nagoyacoffeefes.com/",
    "robots_txt_status": "許可(2026-08確認。Shopify標準構成。admin/cart/checkout/account等のみ制限)",
    "update_cadence": "月次",
    "note": "トップページの「PROJECTs」セクションで日程が明示されている(=開催済みでない)ブランドイベントのみ取得",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「2026/9/19(Sat)-20(Sun)」「2026/10/31(土)-11/1(日)」の両方にマッチ
# (曜日表記が英語/日本語どちらでも括弧の中身は問わない)
DATE_RANGE_PATTERN = re.compile(
    r"(\d{4})/(\d{1,2})/(\d{1,2})\([^)]*\)[-〜](?:(\d{1,2})/)?(\d{1,2})\([^)]*\)"
)


def brand_name(name_part: str) -> str:
    upper = name_part.upper()
    if "HOSHIGAOKA" in upper:
        return "HOSHIGAOKA COFFEE MARKET"
    if "COFFEE JAM" in upper:
        return "COFFEE JAM"
    return "NAGOYA COFFEE FESTIVAL"


def parse_banner(heading_raw: str, text_raw: str):
    """バナー1件分の見出し・本文テキストから、日程が読み取れた場合のみ
    レコードを作る(読み取れない場合は開催済みとみなしNoneを返す)。"""
    heading = re.sub(r"\s+", " ", heading_raw).strip()

    m = DATE_RANGE_PATTERN.search(heading)
    if m:
        # トップの告知バナー: 日程が見出し文に埋め込まれているため取り除く
        heading = (heading[: m.start()] + heading[m.end() :]).strip()
        heading = heading.replace("開催!!", "").strip()
    else:
        m = DATE_RANGE_PATTERN.search(text_raw or "")
        if not m:
            return None

    year, month, day, end_month, end_day = m.groups()
    start_date = f"{year}-{int(month):02d}-{int(day):02d}"
    end_month = end_month or month
    end_date = f"{year}-{int(end_month):02d}-{int(end_day):02d}"

    if "@" in heading:
        name_part, venue_part = (s.strip() for s in heading.split("@", 1))
    else:
        name_part, venue_part = heading, None

    return {
        "brand": brand_name(name_part),
        "name": name_part,
        "venue": venue_part,
        "start_date": start_date,
        "end_date": end_date,
    }


def scrape_events() -> list[dict]:
    resp = requests.get(EVENT_SOURCE_INFO["url"], headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    seen = set()
    records = []
    for box in soup.select(".banner__box"):
        heading_el = box.select_one(".banner__heading")
        if not heading_el:
            continue
        text_el = box.select_one(".banner__text")
        heading_raw = heading_el.get_text(" ", strip=True)
        text_raw = text_el.get_text(" ", strip=True) if text_el else ""

        # 同じスライドショー内で複数スライドが同一テキストを繰り返すため重複除去
        key = (heading_raw, text_raw)
        if key in seen:
            continue
        seen.add(key)

        parsed = parse_banner(heading_raw, text_raw)
        if not parsed:
            continue

        records.append({
            "event_source": parsed["brand"],
            "name": parsed["name"],
            "event_type": "festival",
            "venue": parsed["venue"],
            "start_date": parsed["start_date"],
            "end_date": parsed["end_date"],
            "source_url": EVENT_SOURCE_INFO["url"],
        })
    return records


if __name__ == "__main__":
    import json
    events = scrape_events()
    output = {"event_source": EVENT_SOURCE_INFO, "events": events}
    with open("data_events_ncf.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(events)}件を data_events_ncf.json に出力しました")
