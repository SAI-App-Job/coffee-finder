# -*- coding: utf-8 -*-
"""
scrape_events_ccf.py

COFFEE CITY FESTIVAL(coffee-city-fes.com)の開催概要を取得する。COFFEE CITY
FESTIVAL SAPPORO実行委員会主催、札幌PARCOを主会場に第8回まで継続している
コーヒーの祭典。

【日程・会場情報の取得方法について】実データ確認済み(2026-08時点): トップページ
は「2025.11.28Fri〜12.1Mon」のような日程表示や「vol.8」等をSVG画像として
描画しており、ページ本文のテキストとしては存在しない(視覚的な演出目的の
デザイン)。ただし各画像には`alt`属性でアクセシビリティ用のテキストが
正確に埋め込まれていることを確認した(例: `<img class="date" alt="2025.
11.28Fri〜12.1Mon 平日12:00-19:00 土日10:00-19:00">`、`<img class="vol"
alt="vol.8">`、ロゴ画像`alt="コーヒーシティフェスティバル2025"`)。
本スクレイパーはこれらの`alt`属性からテキストを取得する。会場名
(「札幌PARCO7F スペース７」)は`div.place .name`内に画像に埋め込まれず
通常のテキストとして存在する。

なお「今回の舞台は大阪！」等の文言は今回の出展ロースターの出身地を紹介する
テーマ文であり、実際の開催地(会場)は一貫して札幌PARCOであることを実データで
確認済み。venueには`div.place .name`の実際の会場テキストのみを採用する。

robots.txt確認済み(2026-08時点): robots.txtファイル自体が存在しない(404)。
一般クローラーへの制限記載が無いため、他スクレイパーと同じUser-Agent・
Crawl-Delayで通常のクロール規範に従ってアクセスする。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "COFFEE CITY FESTIVAL(COFFEE CITY FESTIVAL SAPPORO実行委員会)",
    "url": "https://coffee-city-fes.com/",
    "robots_txt_status": "制限なし(2026-08確認。robots.txt自体が存在しない/404)",
    "update_cadence": "月次",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「2025.11.28Fri〜12.1Mon」のような、日付+英語曜日省略形の範囲表記
DATE_RANGE_PATTERN = re.compile(
    r"(\d{4})\.(\d{1,2})\.(\d{1,2})[A-Za-z]*[〜~](?:(\d{1,2})\.)?(\d{1,2})[A-Za-z]*"
)


def scrape_current_event() -> dict:
    """トップページのキービジュアルから、現在/次回開催分のイベント1件を作る。"""
    resp = requests.get(EVENT_SOURCE_INFO["url"], headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    logo_img = soup.select_one(".kv__logo img")
    name = logo_img.get("alt") if logo_img and logo_img.get("alt") else None

    date_img = soup.select_one("img.date")
    date_alt = date_img.get("alt", "") if date_img else ""
    start_date = end_date = None
    m = DATE_RANGE_PATTERN.search(date_alt)
    if m:
        year, month, day, end_month, end_day = m.groups()
        start_date = f"{year}-{int(month):02d}-{int(day):02d}"
        end_month = end_month or month
        end_date = f"{year}-{int(end_month):02d}-{int(end_day):02d}"

    vol_img = soup.select_one("img.vol")
    vol = vol_img.get("alt") if vol_img and vol_img.get("alt") else None

    place_name_el = soup.select_one("div.place .name")
    venue = place_name_el.get_text(strip=True) if place_name_el else None

    return {
        "event_source": EVENT_SOURCE_INFO["name"],
        "name": name,
        "event_type": "festival",
        "venue": venue,
        "start_date": start_date,
        "end_date": end_date,
        "vol": vol,
        "source_url": EVENT_SOURCE_INFO["url"],
    }


if __name__ == "__main__":
    import json
    event = scrape_current_event()
    output = {"event_source": EVENT_SOURCE_INFO, "events": [event]}
    with open("data_events_ccf.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("[done] COFFEE CITY FESTIVAL 現在/次回開催分1件を data_events_ccf.json に出力しました")
