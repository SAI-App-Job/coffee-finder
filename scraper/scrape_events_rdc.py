# -*- coding: utf-8 -*-
"""
scrape_events_rdc.py

Roast Design Coffee(roast-design-coffee.com)の「お知らせ」ブログ(/info)から、
開催予定のセミナー・ワークショップ情報を取得する。27 COFFEE ROASTERSの
scrape_27coffee_seminars.pyと同じ「1講座×1店舗」設計・「現在のみ」方針。

【ページ構成について】実データ確認済み(2026-08時点): カラーミーショップ
(shop-pro.jp)製。/infoの1ページ目に最新5件の記事が新着順(投稿日降順)で並び、
一覧ページ自体に各記事の全文(`div.info_body.wysiwyg`)が既に埋め込まれている
ため、個別記事ページへの追加アクセスは不要。記事は大きく3種類:
  1. 月次テイスティングイベント(例:「9月のテイスティングイベントのお知らせ」)
     — 1記事=1イベント。本文中に「参加費：」「場所：」(コロン区切り、
     同一行)と「◯日程」(見出し行の次から「- 9月6日（日）」のような
     箇条書き日付が続く)という構成。
  2. 月次ワークショップまとめ(例:「8月のワークショップのお知らせ」)—
     1記事に複数のワークショップが「---(ハイフン10個以上)」区切りで
     まとめられている。各ワークショップは「◯開催日時」「◯場所」
     「◯参加費」「◯定員」という見出し行+次行以降に値、という構成
     (見出しの直後に値が来る場合と改行してから来る場合が混在)。
  3. 営業日のお知らせ — 上記の見出し(開催日時/日程/場所/参加費/定員)を
     一切含まないため、本スクレイパーは自然に無視する(除外用の特別な
     判定ロジックは不要)。

見出しの表記揺れ(「◯場所」と「場所：」等)に対応するため、見出し行を
正規表現(LABEL_LINE_PATTERN)で検出し、同一行に値があればそれを、無ければ
次の見出し行が来るまでの後続行を値として集める、行ベースの状態機械で
パースする。日付は「M月D日」を含む行を全て拾い、複数の開催日をそれぞれ
独立したセッションとして扱う(単発イベントの月次まとめでも、日付が1つも
未来を指さなければイベント全体を除外する)。日付の年は記事の投稿日
(info_date)と同じ年と仮定する(実データ確認済み: 告知から開催まで
1ヶ月以内のケースのみ確認できたため)。

【店舗との紐付けについて】実データ確認済み(2026-08時点): 「場所」欄の表記が
shops.jsonのSHOP_LOCATION.label(「本店(マプレ新百合ヶ丘)」「B-side向ヶ丘
遊園・登戸店」)と完全一致しない(語順が違う。例:「新百合ヶ丘本店」)ため、
27coffeeのような部分文字列一致ではなく、店舗ごとのキーワード集合
(SHOP_LOCATION_KEYWORDS)で判定する。1つのワークショップが両店舗で
開催される場合は、27coffeeと同じく店舗ごとに別レコードへ分割する。

robots.txt確認済み(2026-08時点): 「User-agent: * / Allow: /」で全面的に許可。
"""

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

SHOP_NAME = "Roast Design Coffee"
BASE_URL = "https://roast-design-coffee.com"
INFO_URL = f"{BASE_URL}/info"
# /infoの1ページ目に全記事の本文が埋め込まれており、追加リクエストが発生
# しない(1回のfetchで完結する)ため、CRAWL_DELAYは不要
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EVENT_SOURCE_INFO = {
    "name": f"{SHOP_NAME}(roast-design-coffee.com)",
    "url": INFO_URL,
    "robots_txt_status": "許可(2026-08確認。User-agent: * / Allow: / で全面的に許可)",
    "update_cadence": "月次",
    "note": "「お知らせ」ブログの1ページ目(新着順、最新5件)のみが対象。日程が判明している回は未来の開催のみ",
}

# data/shops.jsonのRoast Design Coffee.locations[].labelと一致させる。
# 本文中の表記(「新百合ヶ丘本店」「B-side向ヶ丘遊園・登戸店」等)は
# labelと語順が異なるため、部分一致ではなくキーワード集合で判定する
SHOP_LOCATION_KEYWORDS = {
    "本店(マプレ新百合ヶ丘)": ["新百合ヶ丘", "本店"],
    "B-side向ヶ丘遊園・登戸店": ["B-side", "登戸"],
}

LABEL_LINE_PATTERN = re.compile(r"^[◯○]?\s*(開催日時|日程|場所|会場|参加費|定員)\s*[：:]?\s*(.*)$")
LABEL_KEY_MAP = {
    "開催日時": "date", "日程": "date",
    "場所": "venue", "会場": "venue",
    "参加費": "price",
    "定員": "capacity",
}
SEPARATOR_PATTERN = re.compile(r"^-{10,}$")
MONTH_DAY_PATTERN = re.compile(r"(\d{1,2})月\s*(\d{1,2})日")
POST_DATE_PATTERN = re.compile(r"(\d{4})-\d{2}-\d{2}")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def list_posts() -> list[dict]:
    """1ページ目(新着順)の記事一覧から、タイトル・URL・投稿日・本文を取得する。
    一覧ページ自体に全文が埋め込まれているため、追加リクエストは発生しない。"""
    soup = fetch_soup(INFO_URL)
    posts = []
    for info in soup.select("div.info"):
        title_link = info.select_one(".info_title a")
        date_el = info.select_one(".info_date")
        body_el = info.select_one(".info_body")
        if not title_link or not date_el or not body_el:
            continue
        m = POST_DATE_PATTERN.search(date_el.get_text(strip=True))
        if not m:
            continue
        for br in body_el.find_all("br"):
            br.replace_with("\n")
        posts.append({
            "title": title_link.get_text(strip=True),
            "url": BASE_URL + title_link.get("href"),
            "published_year": int(m.group(1)),
            "body_text": body_el.get_text(),
        })
    return posts


def split_blocks(text: str) -> list[str]:
    """「---(ハイフン10個以上)」区切りで本文をブロックに分割する。
    区切りが無い記事は1ブロックのみを返す(記事全体が1イベント)。"""
    lines = text.split("\n")
    blocks: list[list[str]] = [[]]
    for line in lines:
        if SEPARATOR_PATTERN.match(line.strip()):
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(b) for b in blocks]


def parse_sections(text: str) -> dict:
    """「◯場所」や「場所：」のような見出し行を検出し、同一行の値または
    後続行を、次の見出しが来るまで集める行ベースの状態機械。"""
    sections = {"date": [], "venue": [], "price": [], "capacity": []}
    current_key = None
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = LABEL_LINE_PATTERN.match(line)
        if m:
            label, inline_value = m.groups()
            current_key = LABEL_KEY_MAP[label]
            inline_value = inline_value.strip()
            if inline_value:
                sections[current_key].append(inline_value)
            continue
        if current_key:
            sections[current_key].append(line)
    return sections


def extract_dates(date_lines: list[str], year: int) -> list[str]:
    dates = []
    for line in date_lines:
        m = MONTH_DAY_PATTERN.search(line)
        if m:
            month, day = m.groups()
            dates.append(f"{year}-{int(month):02d}-{int(day):02d}")
    return dates


def match_shop_locations(venue_text: str | None) -> list[str]:
    if not venue_text:
        return []
    matched = []
    for label, keywords in SHOP_LOCATION_KEYWORDS.items():
        if any(kw in venue_text for kw in keywords):
            matched.append(label)
    return matched


def build_records(name: str, sections: dict, published_year: int, source_url: str, today: str) -> list[dict]:
    venue_text = " ".join(sections["venue"]) or None
    if venue_text:
        # 「Roast Design Coffee B-side 向ヶ丘遊園・登戸店　[Map]」のような
        # 地図リンクの原文([Map])が末尾に残ることがあるため取り除く
        venue_text = re.sub(r"\s*\[Map\]\s*$", "", venue_text).strip() or None

    price = " ".join(sections["price"]) or None
    capacity = " ".join(sections["capacity"]) or None
    dates = extract_dates(sections["date"], published_year)

    if not dates:
        # 日程が読み取れない記事(営業日のお知らせ等)は対象外
        return []

    upcoming = sorted(d for d in dates if d >= today)
    if not upcoming:
        return []
    start_date = end_date = upcoming[0]

    matched_labels = match_shop_locations(venue_text) or [None]

    return [
        {
            "shop_name": SHOP_NAME,
            "shop_location_label": label,
            "name": name,
            "venue": venue_text,
            "start_date": start_date,
            "end_date": end_date,
            "duration": None,
            "price": price,
            "capacity": capacity,
            "source_url": source_url,
        }
        for label in matched_labels
    ]


def scrape_seminars() -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    records = []

    # /info の1ページ目に全記事の本文が既に埋め込まれているため、
    # 追加リクエストは発生しない(list_posts内の1回のみ)
    for post in list_posts():
        blocks = split_blocks(post["body_text"])

        if len(blocks) == 1:
            # 区切りが無い記事は、記事全体が1イベント(記事タイトル=イベント名)
            sections = parse_sections(blocks[0])
            records.extend(
                build_records(post["title"], sections, post["published_year"], post["url"], today)
            )
        else:
            # 先頭ブロックは前置き(申込方法の案内等)のため読み飛ばす。
            # 各ブロックの最初の行をワークショップ名として扱う
            for block in blocks[1:]:
                lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
                if not lines:
                    continue
                name = lines[0]
                sections = parse_sections(block)
                records.extend(
                    build_records(name, sections, post["published_year"], post["url"], today)
                )

    return records


if __name__ == "__main__":
    import json
    seminars = scrape_seminars()
    output = {"event_source": EVENT_SOURCE_INFO, "events": seminars}
    with open("data_events_rdc.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(seminars)}件を data_events_rdc.json に出力しました")
