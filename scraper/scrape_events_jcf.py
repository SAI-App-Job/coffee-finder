# -*- coding: utf-8 -*-
"""
scrape_events_jcf.py

Japan Coffee Festival(japancoffeefestival.com)が全国各地で開催するコーヒー
フェスティバルの開催情報を取得する。「実行委員会」形式で運営されており、
個々の開催回はevent-YYYYMMDD-地名.htmlという規則的なURLを持つ。

【データ取得方法について】実データ確認済み(2026-08時点):
トップページは`<script src="data/site-data.js">`を読み込んでおり、このJSファイル
は`window.JCF_DATA = {...};`という形でイベント一覧をまるごとJSON形式で埋め込んで
いる(news配列+events配列)。個々のevent-*.htmlページを1件ずつスクレイピングする
より、この単一のデータソースを直接パースする方が確実かつ軽量なため、こちらを
採用する。events配列には、まだ専用ページが用意されていない直近未来のイベント
(url: null)も含まれる。その場合はイベントソースのトップページURLを代わりに使う。

【コーヒー以外のイベントの除外について】実データ確認済み(2026-08時点):
events配列には「第４回 ウイスキー100年フェスティバル in 島本」という、Japan
Coffee Festivalとは無関係な提携イベントが1件混在していた(同じ運営母体が扱う
別イベントを同じ配列に載せていると見られる。newsセクションにも関連告知あり)。
タイトルに「コーヒー」または"Coffee"を含まないイベントは除外する。

【会場住所の取得について】実データ確認済み(2026-08時点): site-data.jsの
archiveLabelは「京都府・宇治市植物公園」のような都道府県・市区町村レベルの
表記だが、個別ページ(urlが判明しているイベントのみ)には`<dt>会場</dt>
<dd>...</dd>`という構造で、より詳しい会場名が入っており、判明している場合は
「宇治市植物公園（宇治市広野町八軒屋谷25-1）」のように住所も括弧内に含まれる。
個別ページが無い(url未定)イベントはarchiveLabelのまま。個別ページ取得は
site-data.js取得後の追加リクエストになるため、他スクレイパーと同じ
CRAWL_DELAY_SECONDSを1件ごとに空ける。

robots.txt確認済み(2026-08時点): 一般クローラーへは「User-agent: * / Allow: /」
(Content-Signal: search=yes, ai-train=no, use=reference。本スクレイパーの用途
=一次資料としての開催情報参照はuse=referenceに該当)。GPTBot・ClaudeBot・
Amazonbot等の主要AI事業者クローラーは個別に名指しでDisallowされているが、
本スクレイパーは独自のUser-Agent(CoffeeFinderBot/0.1)を使用しており、これらの
名指しリストには該当しないため「User-agent: *」の許可規定が適用される。
/adminのみDisallow(本スクレイパーの対象外)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

EVENT_SOURCE_INFO = {
    "name": "Japan Coffee Festival(実行委員会)",
    "url": "https://japancoffeefestival.com/",
    "robots_txt_status": (
        "許可(2026-08確認。GPTBot/ClaudeBot等主要AI事業者クローラーは個別に禁止されているが、"
        "独自User-Agentは「User-agent: *」の許可規定の対象。Content-Signal: use=referenceにも合致)"
    ),
    "update_cadence": "月次",
}

BASE_URL = "https://japancoffeefestival.com"
SITE_DATA_URL = f"{BASE_URL}/data/site-data.js"
CRAWL_DELAY_SECONDS = 10  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

JCF_DATA_PATTERN = re.compile(r"window\.JCF_DATA\s*=\s*(\{.*\});?\s*$", re.DOTALL)
COFFEE_TITLE_PATTERN = re.compile(r"コーヒー|Coffee", re.IGNORECASE)


def fetch_jcf_data() -> dict:
    resp = requests.get(SITE_DATA_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    m = JCF_DATA_PATTERN.search(resp.text)
    if not m:
        raise ValueError("window.JCF_DATA の埋め込みJSONが見つかりませんでした(サイト構造が変わった可能性)")
    return json.loads(m.group(1))


def build_source_url(raw_url: str | None) -> str:
    if not raw_url:
        # 実データ確認済み: 開催が先のイベントはまだ専用ページ(url)が無い場合がある
        return EVENT_SOURCE_INFO["url"]
    path = raw_url if raw_url.startswith("/") else f"/{raw_url}"
    return f"{BASE_URL}{path}"


def fetch_venue_detail(url: str) -> str | None:
    """個別イベントページの「会場」欄(dt/dd)から、archiveLabelより詳しい
    会場名(判明していれば住所も括弧内に含む)を取得する。"""
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for dt in soup.find_all("dt"):
        if dt.get_text(strip=True) == "会場":
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(" ", strip=True)
    return None


def scrape_events() -> list[dict]:
    data = fetch_jcf_data()
    time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    for event in data.get("events", []):
        title = event.get("title", "")
        if not COFFEE_TITLE_PATTERN.search(title):
            # Japan Coffee Festivalとは無関係な提携イベント(実データ確認済み:
            # 「ウイスキー100年フェスティバル」)を除外する
            continue

        raw_url = event.get("url")
        source_url = build_source_url(raw_url)
        venue = event.get("archiveLabel")
        if raw_url:
            detail_venue = fetch_venue_detail(source_url)
            time.sleep(CRAWL_DELAY_SECONDS)
            if detail_venue:
                venue = detail_venue

        records.append({
            "event_source": EVENT_SOURCE_INFO["name"],
            "name": title,
            "event_type": "festival",
            "venue": venue,
            "start_date": event.get("start"),
            "end_date": event.get("end"),
            "source_url": source_url,
        })
    return records


if __name__ == "__main__":
    events = scrape_events()
    output = {"event_source": EVENT_SOURCE_INFO, "events": events}
    with open("data_events_jcf.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(events)}件を data_events_jcf.json に出力しました")
