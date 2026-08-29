# -*- coding: utf-8 -*-
"""
scrape_27coffee_seminars.py

27 COFFEE ROASTERS(27coffee.jp)の「スクール&イベント」ブログ(/blogs/school-event)
から、開催中(常設・随時受付)または開催予定(具体的な日程がまだ先)のセミナー情報を
取得する。scrape_27coffee.py(商品情報)とは別の関心事のため、専用スクリプトとして
分離している。

【ページ構成について】実データ確認済み(2026-08時点): Shopifyの標準ブログ機能。
新着順(published_at降順)に記事が並び、1ページ目には最新8記事が表示される。
記事は大きく2種類に分かれる:
  1. 常設講座(例: DRIP COFFEE WORKSHOP、LATTE ART WORKSHOP、Barista Step
     School) — 具体的な開催日が無く、「受講場所」欄やスケジュール表の日付欄が
     「予約制」「応相談」のような文言になっている。カレンダー予約や個別
     問い合わせで随時申し込める形式のため、常に「開催中(受付中)」として扱う。
  2. 単発イベント(例: SCAJ2018 Conference & Exhibition、New Crop Cupping) —
     「スケジュール」表に具体的な日付(M月D日)の行がある。すべての日付が
     既に過ぎていれば、そのイベント全体を除外する。

1ページ目より前(2ページ目以降、全7ページ)の記事は2018〜2019年の完全に過去の
イベントであることを実データで確認済みのため(2ページ目を確認、Sep 2019以前
のみ)、本スクレイパーは1ページ目のみを対象とする(TCF/珈琲博覧日と同じ
「現在のみ」設計方針。過去記事を毎回全件取得し直すコストに見合わない)。

【テーブル構造について】実データ確認済み(2026-08時点): 記事本文中の複数の
<table>のうち、先頭行の先頭セル(th/td問わず)が「スケジュール」であるものを
日程表とみなす(class="schoolCalendar"が付く記事とそうでない記事が混在して
いたため、クラス名ではなくセル文言で判定する)。それ以外のtable(所要時間/
受講料/受講場所等がラベル・値の交互配置になっているもの)から概要を拾う。
記事によってラベルセルが<th>のものと<td><strong>のものが混在しているため、
タグ種別を問わずth/td両方をセルとして扱う。

【日付テーブルの構造について】日程未定の講座では、日付列に「予約制」
「応相談」のような非日付文字列が入るため、正規表現(M月D日)にマッチしなければ
「日程未定」として扱う。日付の年は記事の公開日(time[datetime])と同じ年と
仮定する(実データ確認済み: 告知から開催まで数週間以内のケースのみ確認できた
ため)。

【店舗との紐付けについて】実データ確認済み(2026-08時点): 「受講場所」欄や
日程表の「場所」列には、shops.json記載の実店舗ラベル(辻堂本店/CORNER 27/
鎌倉店/坂ノ下店/茅ヶ崎店)がそのまま部分文字列として含まれる形で書かれている
(例:「27 COFFEE ROASTERS TSUJIDO（辻堂本店）」)。1つの講座が複数店舗で
開催される場合(例: DRIP COFFEE WORKSHOPは辻堂本店・鎌倉店の両方)は、
PRODUCTがshop_nameで店舗に紐づくのと同じ考え方で、店舗ごとに1レコードずつ
分けて出力する。既知の店舗ラベルに一致しない会場(東京ビッグサイト等の外部
会場)は、shop_location_labelをnullのまま会場名の原文だけを保持する。

robots.txt確認済み(2026-08時点): scrape_27coffee.pyと同じ標準Shopify
robots.txtで、/blogs/配下も許可対象(/cart・/checkout・/account・/admin等の
みDisallow)。
"""

import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

SHOP_NAME = "27 COFFEE ROASTERS"
BASE_URL = "https://27coffee.jp"
BLOG_URL = f"{BASE_URL}/blogs/school-event"
CRAWL_DELAY_SECONDS = 1  # scrape_27coffee.pyと同じ(robots.txtにCrawl-delay指定なし)
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# aggregate_events.pyが他のイベント情報源(WCC/SCAJ/ACE/...)と同じ形式
# ({"event_source": {...}, "events": [...]})で読み込めるようにするための、
# 共通スキーマに合わせたメタ情報
EVENT_SOURCE_INFO = {
    "name": f"{SHOP_NAME}(27coffee.jp)",
    "url": BLOG_URL,
    "robots_txt_status": "許可(2026-08確認。標準Shopify robots.txt。/blogs/配下も許可対象)",
    "update_cadence": "月次",
    "note": "「スクール&イベント」ブログの1ページ目(新着順)のみが対象。日程が判明している回は未来の開催のみ、日程未定の常設講座は常に含む",
}

# data/shops.jsonの27 COFFEE ROASTERS.locations[].labelと一致させる
SHOP_LOCATION_LABELS = ["辻堂本店", "CORNER 27", "鎌倉店", "坂ノ下店", "茅ヶ崎店"]

MONTH_DAY_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def list_articles() -> list[dict]:
    """1ページ目(新着順)の記事一覧から、タイトル・URL・公開日を取得する。"""
    soup = fetch_soup(BLOG_URL)
    articles = []
    for art in soup.select("article.blog-item"):
        link = art.select_one("a.blog-item__header")
        time_el = art.select_one("time[datetime]")
        if not link or not time_el or not link.get("href"):
            continue
        articles.append({
            "title": (link.get("title") or "").strip(),
            "url": BASE_URL + link.get("href"),
            "published_at": time_el.get("datetime"),
        })
    return articles


def parse_overview_table(table) -> dict:
    """所要時間/受講料/受講場所のようなラベル・値が交互に並ぶ行から辞書を作る。
    メールテンプレートのような単一セル行(申込方法の案内等)は対象外。"""
    data = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2 or len(cells) % 2 != 0:
            continue
        for i in range(0, len(cells), 2):
            label = cells[i].get_text(strip=True)
            value = re.sub(r"\s+", " ", cells[i + 1].get_text(" ", strip=True)).strip()
            if label and value:
                data[label] = value
    return data


def find_schedule_table(soup: BeautifulSoup):
    """先頭行の先頭セルが「スケジュール」であるtableを探す(class名は記事により
    schoolCalendar付き/無しが混在するため、セル文言で判定する)。"""
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        first_cell = first_row.find(["th", "td"])
        if first_cell and first_cell.get_text(strip=True) == "スケジュール":
            return table
    return None


def parse_schedule_rows(table) -> list[dict]:
    """スケジュール表の全行を返す(日付が判明しない「予約制」等の行も含む。
    その場合は常設講座の会場情報として使う)。"""
    rows = []
    for tr in table.find_all("tr")[1:]:  # ヘッダー行をスキップ
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not any(cells):
            continue  # 空の区切り行(実データ確認済み: SCAJ2018記事等にあり)
        rows.append({
            "date_text": cells[0] if len(cells) > 0 else None,
            "time": cells[1] if len(cells) > 1 else None,
            "place": cells[2] if len(cells) > 2 else None,
            "capacity": cells[3] if len(cells) > 3 else None,
        })
    return rows


def match_shop_locations(venue_text: str | None) -> list[str]:
    """会場テキストに含まれる既知の実店舗ラベルをすべて返す(部分文字列一致)。
    どれにも一致しない場合は空リスト(外部会場、または未判定)。"""
    if not venue_text:
        return []
    return [label for label in SHOP_LOCATION_LABELS if label in venue_text]


def build_seminar_records(article: dict, overview: dict, schedule_rows: list[dict], today: str) -> list[dict]:
    duration = overview.get("所要時間")
    price = overview.get("受講料") or overview.get("参加費")
    venue_text = overview.get("受講場所") or overview.get("場所")
    published_year = int(article["published_at"][:4])

    dated_sessions = []
    for row in schedule_rows:
        m = MONTH_DAY_PATTERN.search(row.get("date_text") or "")
        if m:
            month, day = m.groups()
            dated_sessions.append({
                **row,
                "date": f"{published_year}-{int(month):02d}-{int(day):02d}",
            })

    capacity = None
    if dated_sessions:
        # 単発イベント: 日付が判明している回のうち、未来の開催が1つも
        # 無ければイベント全体を開催済みとみなして除外する
        upcoming = [s for s in dated_sessions if s["date"] >= today]
        if not upcoming:
            return []
        session = min(upcoming, key=lambda s: s["date"])
        start_date = end_date = session["date"]
        session_venue = session.get("place") or venue_text
        capacity = session.get("capacity")
    elif schedule_rows:
        # 常設講座(スケジュール表はあるが日付が「予約制」等で未定) — 場所は
        # スケジュール表の値を優先する(概要欄より具体的なことがあるため)
        start_date = end_date = None
        session_venue = schedule_rows[0].get("place") or venue_text
        capacity = schedule_rows[0].get("capacity")
    else:
        # スケジュール表自体が無い常設講座 — 概要欄の受講場所を使う
        start_date = end_date = None
        session_venue = venue_text

    matched_labels = match_shop_locations(session_venue) or [None]

    return [
        {
            "shop_name": SHOP_NAME,
            "shop_location_label": label,
            "name": article["title"],
            "seminar_type": "workshop",
            "venue": session_venue,
            "start_date": start_date,
            "end_date": end_date,
            "duration": duration,
            "price": price,
            "capacity": capacity,
            "source_url": article["url"],
        }
        for label in matched_labels
    ]


def scrape_seminars() -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    records = []

    for article in list_articles():
        soup = fetch_soup(article["url"])
        time.sleep(CRAWL_DELAY_SECONDS)

        schedule_table = find_schedule_table(soup)
        overview = {}
        for table in soup.find_all("table"):
            if table is schedule_table:
                continue
            overview.update(parse_overview_table(table))
        schedule_rows = parse_schedule_rows(schedule_table) if schedule_table is not None else []

        records.extend(build_seminar_records(article, overview, schedule_rows, today))

    return records


if __name__ == "__main__":
    import json
    seminars = scrape_seminars()
    output = {"event_source": EVENT_SOURCE_INFO, "events": seminars}
    with open("data_events_27coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(seminars)}件を data_events_27coffee.json に出力しました")
