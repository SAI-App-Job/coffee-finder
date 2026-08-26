# -*- coding: utf-8 -*-
"""
scrape_events_tcf.py

TOKYO COFFEE FESTIVAL(tokyocoffeefestival.co)の開催概要を取得する。2015年から
続く、NPO法人Farmers Market Association主催・Tokyo Coffee Festival実行委員会
共催のイベント。

【/newsページが使えない理由】実データ確認済み(2026-08時点): /newsは2016〜2018年
の記事28件のみで更新が止まっており(最新記事ですら2018.09.28)、継続的な開催情報
の追跡には使えない。

【トップページから1件のみ取得する設計】実データ確認済み(2026-08時点):
sitemap.xmlを確認したところ、このサイトは「現在/次回の開催回」をルートURL
(tokyocoffeefestival.co)で公開し、それが終わると`tokyo-coffee-festival-YYYY-season`
のような個別URLへ移り、さらに古くなると`/history/`配下へ移動する構造になっている
(例: 2025年冬開催分は`/tokyo-coffee-festival-2025-winter`、2024年分は
`/history/tokyo-coffee-festival-2024`)。つまりルートURLは常に「現在/次回の1件」
しか保持しておらず、SCAJスクレイパーと同じ「年次(季節ごと)イベント1件」方式で
十分。過去開催回のアーカイブ収集は本スクレイパーのスコープ外とする。

【Outlineセクションの構造】実データ確認済み(2026-08時点): トップページの
`#top-outline`セクション内、`.content-body`に`<h3>`(イベント名)と`<ul><li>`
(日程/入場料/場所/主催/共催/連絡、全角コロン「：」区切りのラベル:値形式)が
収まっている。SCAJスクレイパーと同じ「汎用キーバリュー抽出」方式を採用する。

robots.txt確認済み(2026-08時点): 「User-agent: * / Disallow: /cms/wp-admin/」
のみで、トップページを含む一般コンテンツは対象外。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "TOKYO COFFEE FESTIVAL(NPO法人Farmers Market Association)",
    "url": "https://tokyocoffeefestival.co/",
    "robots_txt_status": "許可(2026-08確認。/cms/wp-admin/のみ制限)",
    "update_cadence": "月次",
    "note": "トップページのOutlineセクションが保持するのは現在/次回開催分の1件のみ。過去開催回のアーカイブは収集対象外",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「2026年5月2日」のような完全な日付、および「〜5月4日」のように年を省略した
# 終了日表記の両方にマッチする(実データ確認済み: 終了日側でも月は省略されない)
DATE_TOKEN_PATTERN = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")


def fetch_outline() -> tuple[str | None, dict]:
    """トップページの#top-outlineセクションから、イベント名とラベル:値の
    辞書(日程/入場料/場所/主催/共催/連絡)を取得する。"""
    resp = requests.get(EVENT_SOURCE_INFO["url"], headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    section = soup.select_one("#top-outline")
    if not section:
        raise ValueError("#top-outline セクションが見つかりませんでした(サイト構造が変わった可能性)")

    name_el = section.select_one(".content-body h3")
    name = name_el.get_text(strip=True) if name_el else None

    data = {}
    for li in section.select(".content-body ul li"):
        text = li.get_text(strip=True)
        if "：" not in text:
            continue
        label, _, value = text.partition("：")
        data[label.strip()] = value.strip()

    return name, data


def extract_date_range(text: str):
    """「日程」欄のフリーテキストから開始日・終了日を推定する。年が省略された
    トークン(終了日側)は、直前に出てきた完全な日付の年を引き継いで補完する。"""
    last_year = None
    dates = []
    for m in DATE_TOKEN_PATTERN.finditer(text):
        year, month, day = m.groups()
        if year:
            last_year = year
        elif not last_year:
            continue
        y = year or last_year
        dates.append(f"{y}-{int(month):02d}-{int(day):02d}")

    if not dates:
        return None, None
    return min(dates), max(dates)


def scrape_current_event() -> dict:
    """トップページのOutlineセクションから、現在/次回開催分のイベント1件を作る。"""
    name, data = fetch_outline()

    start_date, end_date = extract_date_range(data.get("日程", ""))

    return {
        "event_source": EVENT_SOURCE_INFO["name"],
        "name": name,
        "event_type": "festival",
        "venue": data.get("場所"),
        "start_date": start_date,
        "end_date": end_date,
        "admission": data.get("入場料"),
        "organizer": data.get("主催"),
        "co_organizer": data.get("共催"),
        "source_url": EVENT_SOURCE_INFO["url"],
    }


if __name__ == "__main__":
    import json
    event = scrape_current_event()
    output = {"event_source": EVENT_SOURCE_INFO, "events": [event]}
    with open("data_events_tcf.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("[done] Tokyo Coffee Festival 現在/次回開催分1件を data_events_tcf.json に出力しました")
