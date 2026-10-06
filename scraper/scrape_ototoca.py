# -*- coding: utf-8 -*-
"""
scrape_ototoca.py

ototoca(ototoca.com、運営は株式会社ワールドコーヒー、広島県広島市西区楠木町。音から選ぶコーヒー通販
ブランド)の商品情報を取得する。EC-CUBE 4系(/products/list・/products/detail/{id})。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
特定商取引法に基づく表記(/help/tradelaw)で実データ確認済み(2026-10時点): 「販売業者 株式会社
ワールドコーヒー 所在地 〒733-0002 広島県広島市西区楠木町2丁目11-10」(本社)。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧(/products/list、18件・1ページ)の全商品が100g入りの
ブレンドコーヒー(音で選ぶ7つのコーヒー7、野塾ブレンド7、受け継がれるブレンド3、極苦ブレンド1を
カテゴリ重複を除いた18件)。全商品が100g・810円(税込)で、シングルオリジン・セット・器具は無い。
重量違い・粉の別商品は無い(挽き方は同一商品の選択肢)。

【焙煎度・ブレンド原産国について】
商品ページの「TASTE PROFILE」欄(「挽き方の選び方」まで)に、一部商品のみ焙煎度(深煎り/中深煎り/極深煎り等)が、「ブレンド原産国」欄に
使用国(割合は非公開、一部商品は欄自体が無い)が記載されている。焙煎度の記載が無い商品のうち、カテゴリ「深煎り・強い苦味」(category_id=6)に属するものは「深煎り」とし、それ以外はNone。焙煎度はroast_hintに保持し、原産国はblend_components
(percentage=None)に記録する。「他」は国名ではないため除外する。

【在庫・価格について】
価格は税込(「￥810 税込」表記)。在庫は商品ページのJSON-LD(schema.org Offer.availability)の
InStock/OutOfStockで判定する。

【robots.txtについて】
User-agent: *はDisallow: /*.csv$のみ(実データ確認済み、2026-10)。商品ページは許可。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "ototoca",
    "url": "https://ototoca.com/",
    "platform": "EC-CUBE",
    "address": "広島県広島市西区楠木町2丁目11-10",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/*.csv$のみDisallow)",
}

BASE_URL = "https://ototoca.com"
LIST_URL = BASE_URL + "/products/list?disp_number=2&pageno={page}"
MAX_PAGES = 5
DEEP_ROAST_CATEGORY_ID = 6
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_SPLIT = '<li class="ec-shelfGrid__item">'
WEIGHT_PATTERN = re.compile(r"[（(]\s*(\d+)\s*g\s*[）)]")
PRICE_PATTERN = re.compile(r"[￥¥]\s*([\d,]+)")
PROFILE_PATTERN = re.compile(r"TASTE PROFILE (.*?) 挽き方の選び方を見る")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
BLEND_ORIGIN_PATTERN = re.compile(r"ブレンド原産国 (.*?) 挽き方の選び方")
AVAILABILITY_PATTERN = re.compile(r'"availability":\s*"https?://schema.org/(\w+)"')
ORIGIN_NAME_FIXES = {"グァテマラ": "グアテマラ"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def clean_text(fragment: str) -> str:
    fragment = re.sub(r"<style.*?</style>|<script.*?</script>", "", fragment, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        html_text = fetch_html(LIST_URL.format(page=page))
        new = 0
        for block in html_text.split(ITEM_SPLIT)[1:]:
            pid_m = re.search(r"/products/detail/(\d+)", block)
            if not pid_m or pid_m.group(1) in items:
                continue
            new += 1
            head = re.sub(r"<style.*?</style>", "", block.split("<form")[0], flags=re.S)
            paragraphs = [clean_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", head, flags=re.S)]
            paragraphs = [p for p in paragraphs if p]
            price_m = PRICE_PATTERN.search(head.replace("\n", " "))
            symbol = None
            if "ototoca-list-symbol" in head:
                symbol = paragraphs[0] if paragraphs else None
                paragraphs = paragraphs[1:]
            name = paragraphs[0] if paragraphs else None
            items[pid_m.group(1)] = {
                "pid": pid_m.group(1),
                "name": name,
                "symbol": symbol,
                "description": paragraphs[1] if len(paragraphs) > 1 and not PRICE_PATTERN.fullmatch(paragraphs[1]) else None,
                "list_price": int(price_m.group(1).replace(",", "")) if price_m else None,
            }
        if new == 0:
            break
        time.sleep(0.5)
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    html_text = fetch_html(f"{BASE_URL}/products/detail/{pid}")
    text = clean_text(html_text)
    profile_m = PROFILE_PATTERN.search(text)
    roast_m = ROAST_PATTERN.search(profile_m.group(1)) if profile_m else None
    origin_m = BLEND_ORIGIN_PATTERN.search(text)
    avail_m = AVAILABILITY_PATTERN.search(html_text)
    return {
        "roast": roast_m.group(1) if roast_m else None,
        "blend_origins": origin_m.group(1) if origin_m else None,
        "availability": avail_m.group(1) if avail_m else None,
    }


def build_record(item: dict) -> dict | None:
    name = item["name"]
    if not name:
        return None
    weight_m = WEIGHT_PATTERN.search(name)
    if not weight_m:
        return None
    weight_g = int(weight_m.group(1))
    detail = fetch_detail(item["pid"])

    raw_name = f"{name} {item['symbol']}" if item["symbol"] else name
    raw_name = unicodedata.normalize("NFKC", raw_name)
    parsed = parse_product(raw_name)
    if parsed["is_flavored"]:
        return None

    components = []
    if detail["blend_origins"]:
        for token in re.split(r"[・、,/]", detail["blend_origins"]):
            token = token.strip()
            if not token or token == "他":
                continue
            token = ORIGIN_NAME_FIXES.get(token, token)
            components.append({"origin_country": detect_country_name(token) or token, "percentage": None})

    sold_out = detail["availability"] is not None and detail["availability"] != "InStock"
    description = item["description"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": "ブレンド",
        "origin_country": None,
        "origin_source": None,
        "designated_brand": None,
        "processing_method": None,
        "grade": None,
        "roast_level": parsed["roast_level"],
        "roast_hint": detail["roast"],
        "roast_selectable": False,
        "flavor_notes": description[:400] if description else None,
        "farm_note": None,
        "post_processing_tags": [],
        "blend_components": components,
        "price": item["list_price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/products/detail/{item['pid']}",
    }


def fetch_deep_roast_pids() -> set[str]:
    """カテゴリ「深煎り・強い苦味」(category_id=6)に属する商品IDを返す。"""
    html_text = fetch_html(f"{BASE_URL}/products/list?category_id={DEEP_ROAST_CATEGORY_ID}&disp_number=2")
    return set(re.findall(r"/products/detail/(\d+)", html_text.split("ec-shelfRole")[-1]))


def scrape_all_products() -> list[dict]:
    records = []
    deep_pids = fetch_deep_roast_pids()
    for item in list_items():
        try:
            record = build_record(item)
            if record is not None and record["roast_hint"] is None and item["pid"] in deep_pids:
                record["roast_hint"] = "深煎り"
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ototoca.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ototoca.json に出力しました")


if __name__ == "__main__":
    main()
