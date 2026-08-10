# -*- coding: utf-8 -*-
"""
scrape_events_ace.py

ACE(Alliance for Coffee Excellence)/Cup of Excellence(cupofexcellence.org)の
年間開催カレンダーを取得する。COE(Cup of Excellenceオークション日)と
NW(National Winner審査週間)を国ごとに取得する。

【重要な制約】トップページのカレンダーウィジェットには年(西暦)の表記が
含まれていない(2026年シーズンの案内であることは記事等の文脈から分かるが、
ページのテキスト自体には出てこない)。そのため、スクレイパー実行時に
season_year を明示的に渡す必要がある。将来的にページ内の別要素(年度切替
ボタン等)から自動取得できないか、実際のHTML確認時に再検討する。

サイト構造(2026年8月確認・web_fetch経由): 国名が2回連続する独特のテキスト
パターン(画像altテキストとラベルが重複していると推測)。「国名 国名 COE: 月 日
[NW: 月 日 – 日]」という並びを正規表現で抽出する。WCCと同様、装飾的な
フロントエンド実装のため、CSS構造よりテキストパターンでの抽出を優先する
設計判断とした。robots.txtは未確認(web_fetchでの取得自体は成功しているため
致命的な禁止はないと推測されるが、実運用前に明示的な確認を推奨)。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "ACE(Alliance for Coffee Excellence)/ Cup of Excellence",
    "url": "https://cupofexcellence.org/",
    "robots_txt_status": "未確認(web_fetch経由の取得は成功。実運用前に要確認)",
    "update_cadence": "月次(シーズンごとにカレンダーが更新される)",
}

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

MONTH_MAP = {
    "January": 1, "Jan": 1, "February": 2, "Feb": 2, "March": 3, "Mar": 3,
    "April": 4, "Apr": 4, "May": 5, "June": 6, "Jun": 6, "July": 7, "Jul": 7,
    "August": 8, "Aug": 8, "September": 9, "Sep": 9, "October": 10, "Oct": 10,
    "November": 11, "Nov": 11, "December": 12, "Dec": 12,
}

# 「国名 国名 COE: 月 日 [NW: 月 日 – 日]」パターン
EVENT_PATTERN = re.compile(
    r"(?P<country>[A-Za-zÀ-ÿ]+(?:\s[A-Za-zÀ-ÿ]+)?)\s+(?P=country)\s+"
    r"COE:\s+(?P<coe_month>[A-Za-z]+\.?)\s+(?P<coe_day>\d{1,2})"
    r"(?:\s+NW:\s+(?P<nw_start_month>[A-Za-z]+\.?)\s+(?P<nw_start_day>\d{1,2})\s*[\u2013-]\s*"
    r"(?:(?P<nw_end_month>[A-Za-z]+\.?)\s+)?(?P<nw_end_day>\d{1,2}))?"
)


def fetch_page_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.get_text(separator=" ")


def _to_date(year: int, month_name: str, day: str) -> str | None:
    month = MONTH_MAP.get(month_name.rstrip("."))
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d}"


def scrape_calendar(season_year: int) -> list[dict]:
    """トップページのカレンダーウィジェットから、国ごとのCOE/NW日程を取得する。

    season_year: カレンダーが対象とする西暦年。ページのテキスト自体に年の
    表記がないため、呼び出し側で明示的に指定する必要がある
    (例: 直近の案内記事や年度切替の確認結果を踏まえて設定)。
    """
    text = fetch_page_text(EVENT_SOURCE_INFO["url"])

    records = []
    for m in EVENT_PATTERN.finditer(text):
        d = m.groupdict()
        coe_date = _to_date(season_year, d["coe_month"], d["coe_day"])

        nw_start_date, nw_end_date = None, None
        if d["nw_start_day"]:
            nw_start_date = _to_date(season_year, d["nw_start_month"], d["nw_start_day"])
            end_month = d["nw_end_month"] or d["nw_start_month"]
            nw_end_date = _to_date(season_year, end_month, d["nw_end_day"])

        records.append({
            "event_source": EVENT_SOURCE_INFO["name"],
            "name": f"{d['country']} Cup of Excellence {season_year}",
            "event_type": "auction",
            "related_country": d["country"],
            "coe_auction_date": coe_date,  # オークション当日
            "national_winner_start_date": nw_start_date,  # 審査週間の開始日(nullable)
            "national_winner_end_date": nw_end_date,  # 審査週間の終了日(nullable)
            "source_url": EVENT_SOURCE_INFO["url"],
        })

    return records


if __name__ == "__main__":
    import json
    import datetime

    # 実行時点で明確な年度情報がページから取得できないため、暫定的に
    # 「現在年の翌年」をデフォルトとする(CoEシーズンは例年、告知の翌年に
    # 開催されることが多いため)。実運用前に実際のページで年度を確認し、
    # 明示的に season_year を指定することを推奨する。
    default_year = datetime.datetime.now().year
    events = scrape_calendar(season_year=default_year)

    output = {"event_source": EVENT_SOURCE_INFO, "events": events}
    with open("data_events_ace.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(events)}件を data_events_ace.json に出力しました(season_year={default_year}、要確認)")
