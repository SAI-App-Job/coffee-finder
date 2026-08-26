# -*- coding: utf-8 -*-
"""
scrape_events_ocx.py

珈琲博覧日(onedaycoffeeexpo.com、名古屋市)の開催概要を取得する。
珈琲博覧日実行委員会・FabCafe Nagoya主催、2022年から続く東海地区最大級の
コーヒーフェス(年1回)。

【アーカイブ構造について】実データ確認済み(2026-08時点): `/index.php/archive/`
ページから、2022〜2025年の各回が`hakuranbi{YYYY}`(2022年のみ`onedaycoffeeexpo2022`)
という規則的なURLで個別ページ化されていることを確認した。これは本イベントが
長期にわたり同じ運営体制・サイト構造で継続している裏付けとして扱い、
トップページの開催概要が毎年同じ場所・同じ書式で更新され続ける前提が
妥当であると判断した。ただし本スクレイパーが実際に取得するのは、
アプリのイベントスケジュールに必要な「現在/次回開催分」のみであり、
トップページ(TCF/SCAJと同じ設計)を対象とする。過去回のアーカイブページを
遡って収集することはスコープ外。

【トップページの構造】実データ確認済み(2026-08時点): Elementor(WordPress)
製。開催概要は`<p><strong>開催日：2026年11月3日（火・祝）10:00-17:00<br>
開催場所：Hisaya-odori Park（久屋大通公園）ケヤキヒロバ・シバフヒロバ、
FabCafe Nagoya</strong></p>`という、`<br>`区切りで「開催日：」「開催場所：」
の2行が1つの`<strong>`要素に収まる形。要素のクラス名はElementor自動生成の
ID(`elementor-element-XXXXXXX`)で不安定なため、WCCスクレイパーと同様に
「開催日」「開催場所」という項目名そのものをテキストから検索する方式を採る。

robots.txt確認済み(2026-08時点): 「User-agent: * / Disallow: /wp-admin/」のみで、
トップページを含む一般コンテンツは対象外。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "珈琲博覧日(珈琲博覧日実行委員会 / FabCafe Nagoya)",
    "url": "https://onedaycoffeeexpo.com/",
    "robots_txt_status": "許可(2026-08確認。/wp-admin/のみ制限)",
    "update_cadence": "月次",
    "note": "トップページが保持するのは現在/次回開催分の1件のみ。2022年からのアーカイブページ(hakuranbi{YYYY})は収集対象外",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「2026年11月3日」のような単日の日付(このイベントは1日開催のため範囲表記は無い)
DATE_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def fetch_outline_text() -> str | None:
    """トップページから「開催日」「開催場所」を含む<strong>ブロックのテキストを
    取得する(<br>は改行として扱う)。"""
    resp = requests.get(EVENT_SOURCE_INFO["url"], headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for strong in soup.find_all("strong"):
        text = strong.get_text()
        if "開催日" in text and "開催場所" in text:
            return text
    return None


def parse_outline(text: str) -> dict:
    data = {}
    for line in text.split("\n"):
        if "：" not in line:
            continue
        label, _, value = line.partition("：")
        data[label.strip()] = value.strip()
    return data


def scrape_current_event() -> dict:
    """トップページの開催概要から、現在/次回開催分のイベント1件を作る。"""
    text = fetch_outline_text()
    if not text:
        raise ValueError("「開催日」「開催場所」を含むブロックが見つかりませんでした(サイト構造が変わった可能性)")

    data = parse_outline(text)

    date_text = data.get("開催日", "")
    m = DATE_PATTERN.search(date_text)
    start_date = end_date = None
    year = None
    if m:
        year, month, day = m.groups()
        start_date = end_date = f"{year}-{int(month):02d}-{int(day):02d}"

    # サイト自身のアーカイブURL命名規則(hakuranbi{YYYY})と一致させ、
    # 「珈琲博覧日{開催年}」という名称で統一する
    name = f"珈琲博覧日{year}" if year else None

    return {
        "event_source": EVENT_SOURCE_INFO["name"],
        "name": name,
        "event_type": "festival",
        "venue": data.get("開催場所"),
        "start_date": start_date,
        "end_date": end_date,
        "source_url": EVENT_SOURCE_INFO["url"],
    }


if __name__ == "__main__":
    import json
    event = scrape_current_event()
    output = {"event_source": EVENT_SOURCE_INFO, "events": [event]}
    with open("data_events_ocx.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("[done] 珈琲博覧日 現在/次回開催分1件を data_events_ocx.json に出力しました")
