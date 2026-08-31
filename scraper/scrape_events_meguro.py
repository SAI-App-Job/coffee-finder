# -*- coding: utf-8 -*-
"""
scrape_events_meguro.py

COFFEE ROASTERY MEGURO(roasterymeguro.com)の「固定表示(sticky)」投稿から、
予約制の焙煎体験セミナー情報を取得する。27 COFFEE ROASTERSの
scrape_27coffee_seminars.pyと同じ「1講座×1店舗」設計。

【投稿の特定方法について】実データ確認済み(2026-08時点): WordPress製で、
REST API(`/wp-json/wp/v2/posts?sticky=true`)が有効。トップページのブログ
一覧には商品紹介・お知らせ等コーヒーセミナーと無関係な投稿も多数混在して
いるが、「焙煎体験セミナー(焙煎からエスプレッソ抽出まで)」という投稿だけが
`sticky: true`(サイト運営者が常時先頭表示に固定している)であることを確認
した。タイトルにキーワードを含むかで判定するより、この「運営者が意図的に
常設案内として固定している」という明示的なシグナルの方が確実なため、
sticky投稿のみを対象とする。

【日程が無い理由】実データ確認済み(2026-08時点): 具体的な開催日はなく、
「以下からお問い合わせをお願いします　日時人数をお知らせください」という
メール予約制(coffeeroasterym@gmail.com宛)。「平日10:00〜／14:00〜／17:00〜、
土日10:00〜／17:00〜」という受付可能な曜日・時間帯の案内はあるが、特定の
日付ではないため、27coffeeの常設講座と同じくstart_date=Noneの「随時受付中」
として扱う。

【会場について】実データ確認済み: 本文中に会場名の明記は無いが、
data/shops.jsonのCOFFEE ROASTERY MEGUROはshop_type=single_location(実店舗
1件のみ、SHOP_LOCATION.labelもnull)であるため、店舗名をそのままvenueとして
扱う(単一店舗のため店舗特定の曖昧さが無い)。

【本文からの項目抽出について】実データ確認済み(2026-08時点): 本文中の
`<ul><li>...</li></ul>`のうち、「所要時間」「セミナー費」で始まる項目、
および人数を含み「まで」を伴う項目(例:「1回あたり最大2名まで」)を、
それぞれ所要時間・受講料・定員として拾う。

robots.txt確認済み(2026-08時点): 標準的なWordPress robots.txtで、
「User-agent: * / Disallow: /wp-admin/」のみ制限。
"""

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
import requests

SHOP_NAME = "COFFEE ROASTERY MEGURO"
BASE_URL = "https://roasterymeguro.com"
STICKY_POSTS_API = f"{BASE_URL}/wp-json/wp/v2/posts?sticky=true"
CRAWL_DELAY_SECONDS = 10  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EVENT_SOURCE_INFO = {
    "name": f"{SHOP_NAME}(roasterymeguro.com)",
    "url": BASE_URL,
    "robots_txt_status": "許可(2026-08確認。標準WordPress robots.txt。/wp-admin/のみ制限)",
    "update_cadence": "月次",
    "note": "固定表示(sticky)投稿のみを対象とする。具体的な開催日は無く、メール予約制(常に「開催中」扱い)",
}

PRICE_PREFIXES = ("セミナー費", "参加費", "受講料")
CAPACITY_PATTERN = re.compile(r"\d+(?:名|組)")


def parse_list_items(items: list[str]) -> dict:
    """<li>の各項目テキストから、所要時間・受講料・定員を抽出する。"""
    result: dict[str, str] = {}
    for text in items:
        if text.startswith("所要時間"):
            result["duration"] = text[len("所要時間"):].strip()
            continue
        matched_price = next((p for p in PRICE_PREFIXES if text.startswith(p)), None)
        if matched_price:
            result["price"] = text[len(matched_price):].strip()
            continue
        if CAPACITY_PATTERN.search(text) and "まで" in text:
            result["capacity"] = text.strip()
    return result


def scrape_seminars() -> list[dict]:
    resp = requests.get(STICKY_POSTS_API, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    posts = resp.json()

    records = []
    for post in posts:
        title = BeautifulSoup(post["title"]["rendered"], "html.parser").get_text(strip=True)
        soup = BeautifulSoup(post["content"]["rendered"], "html.parser")
        items = [li.get_text(strip=True) for li in soup.select("ul.wp-block-list li")]
        fields = parse_list_items(items)

        records.append({
            "shop_name": SHOP_NAME,
            "shop_location_label": None,  # 実店舗1件のみのため店舗特定は不要
            "name": title,
            "venue": SHOP_NAME,
            "start_date": None,  # 固定日程なし(メール予約制のため常に「開催中」扱い)
            "end_date": None,
            "duration": fields.get("duration"),
            "price": fields.get("price"),
            "capacity": fields.get("capacity"),
            "source_url": post["link"],
        })
    return records


if __name__ == "__main__":
    import json
    seminars = scrape_seminars()
    output = {"event_source": EVENT_SOURCE_INFO, "events": seminars}
    with open("data_events_meguro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(seminars)}件を data_events_meguro.json に出力しました")
