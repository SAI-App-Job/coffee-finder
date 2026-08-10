# -*- coding: utf-8 -*-
"""
scrape_events_scaj.py

SCAJ(日本スペシャルティコーヒー協会)が主催する年次展示会「SCAJワールド
スペシャルティコーヒーカンファレンス&エキシビション」の開催概要を取得する。

【重要な制約】協会本体サイト(scaj.org)はrobots.txtで自動アクセスを禁止しており、
「利き珈琲選手権」「コーヒーマイスター講座」等の細かい国内イベント情報は
このサイトからは収集できない。取得できるのは、展示会専用サイト
(scajconference.jp)に掲載される年次旗艦イベント1件のみ。

サイト構造(2026年8月確認): Webflow製。div.event_list > div.event_row の
繰り返しで、各行が h2.event_label(項目名)+ div.event_data(内容)の
キーバリュー形式。PHILOCOFFEAのBEANS DATA表と同じ「汎用キーバリュー抽出」
方式を採用している。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "SCAJ(日本スペシャルティコーヒー協会)ワールドスペシャルティコーヒーカンファレンス&エキシビション",
    "url": "https://scajconference.jp/overview",
    "robots_txt_status": "許可(2026-08確認。scaj.org本体は不可だが展示会専用サイトは対象外項目なし)",
    "update_cadence": "年次(開催概要ページが年度ごとに更新される)",
    "note": "協会本体サイト(scaj.org)はrobots.txtでアクセス禁止。国内の小規模イベント(コーヒーマイスター講座等)は収集不可",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「YYYY年M月D日」形式の日付、および「〜D日」のように年月を省略した
# 範囲表記の終了日を検出するパターン
FULL_DATE_PATTERN = re.compile(r"(\d{4})年(\d{1,2})[⽉月](\d{1,2})日")
RANGE_END_DAY_PATTERN = re.compile(r"[〜~](\d{1,2})日")


def fetch_event_rows(url: str) -> dict:
    """div.event_row の繰り返しから、項目名→内容のキーバリュー辞書を作る。"""
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # <br>と<h3>副見出しを改行として扱う(隣接テキストの巻き込み防止。
    # PHILOCOFFEAスクレイパー実装時に経験した不具合と同種の対策)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for h3 in soup.find_all("h3", class_="event_data_sub_title"):
        h3.insert_before("\n")

    data = {}
    for row in soup.select("div.event_row"):
        label_el = row.select_one("h2.event_label")
        data_el = row.select_one("div.event_data")
        if label_el and data_el:
            text = re.sub(r"\n{2,}", "\n", data_el.get_text()).strip()
            data[label_el.get_text(strip=True)] = text
    return data


def extract_date_range(text: str):
    """「会期」欄のフリーテキストから、最初と最後に出てくる日付を
    開始日・終了日として推定する(複数会場・複数日程が併記されるため)。

    日本語の日程表記は「14日(水)〜16日(金)」のように、範囲の終了日側で
    年・月を省略することが多い。その場合は直前に出てきた完全な日付
    (年・月)を引き継いで補完する。
    """
    last_year, last_month = None, None
    # 完全な日付と「〜D日」の省略表記を、出現順に混ぜて処理する
    tokens = []
    for m in FULL_DATE_PATTERN.finditer(text):
        tokens.append((m.start(), "full", m.groups()))
    for m in RANGE_END_DAY_PATTERN.finditer(text):
        tokens.append((m.start(), "day_only", m.group(1)))
    tokens.sort(key=lambda t: t[0])

    dates = []
    for _, kind, value in tokens:
        if kind == "full":
            year, month, day = value
            last_year, last_month = year, month
            dates.append(f"{year}-{int(month):02d}-{int(day):02d}")
        elif kind == "day_only" and last_year and last_month:
            dates.append(f"{last_year}-{int(last_month):02d}-{int(value):02d}")

    if not dates:
        return None, None
    return min(dates), max(dates)


def scrape_annual_event() -> dict:
    """展示会概要ページから年次イベント1件分のレコードを作る。"""
    data = fetch_event_rows(EVENT_SOURCE_INFO["url"])

    start_date, end_date = extract_date_range(data.get("会期", ""))

    return {
        "event_source": EVENT_SOURCE_INFO["name"],
        "name": data.get("名称", "").replace("\n", " "),
        "event_type": "exhibition",
        "venue": data.get("会場", "").replace("\n", " "),
        "start_date": start_date,
        "end_date": end_date,
        "date_range_raw": data.get("会期"),  # 会場ごとに日程が異なるため原文も保持
        "theme": next((v for k, v in data.items() if k.endswith("テーマ")), None),
        "organizer": data.get("主催", "").replace("\n", " "),
        "admission": data.get("入場料"),
        "source_url": EVENT_SOURCE_INFO["url"],
    }


if __name__ == "__main__":
    import json
    event = scrape_annual_event()
    output = {"event_source": EVENT_SOURCE_INFO, "events": [event]}
    with open("data_events_scaj.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("[done] SCAJ年次イベント1件を data_events_scaj.json に出力しました")
