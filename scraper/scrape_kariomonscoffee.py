# -*- coding: utf-8 -*-
"""
scrape_kariomonscoffee.py

KARIOMONS COFFEE(カリオモンズコーヒー、運営: 株式会社カリオモンズ、
長崎県長崎市茂里町1-42 印刷工場跡1F、カラーミーショップ/shop-pro.jp)の
商品情報を取得する。静岡県のかりおもん(scrape_kariomon.py)とは別店舗。

【ストアURLについて】
指示のあった shop.kariomons.com は実行環境から名前解決できなかった
(2026-10-18)。サイト内リンクは shop.kariomons.com と
kariomons.shop-pro.jp の双方を指しており同一ストアのため、
kariomons.shop-pro.jp を使用する。

robots.txt確認済み(2026-10-18): User-agent: * は /secure/ と /cart/ のみ
禁止(他のshop-pro.jp系店舗と同一)。公式サイト kariomons.com/robots.txt は
/wp/wp-admin/ のみ禁止。

【商品選別】
「コーヒー豆」カテゴリ(cbid=782391、サブカテゴリ: ダイレクトトレード/
コーヒートラベラーズ/スペシャルロット/ブレンド)全82商品を取得。
- 「選べるコーヒーセット」(豆・粉)の2件はセットのため除外。
- 同一銘柄が重量違い(150g/500g/1kg、90g/500g)で別商品として並ぶため、
  最小重量の商品を代表1件とする(500g・1kgは除外)。

【在庫について】
カラーミー側は在庫管理なし(inventory_control: none)で、売り切れ表示が
一切無い。公式サイト kariomons.com/onlineshop の現行ラインナップに
「Sold Out」表記がある銘柄のみ品切れとして反映する。

【産地・焙煎度・風味について】
カラーミーの商品ページは説明文が無い(meta descriptionも全商品共通)。
そのため公式サイト(kariomons.com)から補完する。
- 産地: 公式の農園一覧(/farm)の「農園名 → 地域(国)」で補完。
- 焙煎度・風味・産地・品切れ: 公式 /onlineshop の現行ラインナップ
  (シングル6種+ブレンド3種)に載っている銘柄のみ補完。
公式に載っていない銘柄は null のまま(推測しない)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "KARIOMONS COFFEE",
    "url": "https://kariomons.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "長崎県長崎市茂里町1-42 印刷工場跡1F",
    "prefecture": "長崎県",
    "robots_txt_status": "許可(2026-10-18確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://kariomons.shop-pro.jp/"
CATEGORY_URL = BASE_URL + "?mode=cate&cbid=782391&csid=0&page={page}"
OFFICIAL_SHOP_URL = "https://kariomons.com/onlineshop"
OFFICIAL_FARM_URL = "https://kariomons.com/farm"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 2

NON_BEAN_KEYWORDS = ["セット"]
WEIGHT_PATTERN = re.compile(r"[(（]\s*(\d+(?:\.\d+)?)\s*(kg|g)\s*[)）]", re.IGNORECASE)
ROAST_LABELS = {
    "Light": "浅煎り",
    "Light Medium": "中浅煎り",
    "Medium": "中煎り",
    "Medium Dark": "中深煎り",
    "Dark": "深煎り",
}
COUNTRY_JA = {
    "NICARAGUA": "ニカラグア",
    "EL SALVADOR": "エルサルバドル",
    "HONDURAS": "ホンジュラス",
}


def get(url: str, encoding: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = encoding
    return BeautifulSoup(resp.text, "html.parser")


def norm_key(name: str) -> str:
    """重量表記・空白・ダッシュ表記ゆれを除いた照合用キー。"""
    s = WEIGHT_PATTERN.sub("", name)
    s = re.sub(r"[–—―－]", "-", s)
    s = re.sub(r"\s+", "", s)
    s = s.replace("(", "").replace(")", "")
    return s


def weight_g_from_name(name: str) -> float | None:
    m = WEIGHT_PATTERN.search(name)
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2).lower() == "kg":
        v *= 1000
    return int(v) if v == int(v) else v


def parse_price(text: str) -> int | None:
    m = re.search(r"([\d,]+)\s*円", text)
    return int(m.group(1).replace(",", "")) if m else None


def scrape_list() -> list[dict]:
    items = []
    seen = set()
    for page in range(1, 20):
        soup = get(CATEGORY_URL.format(page=page), "euc-jp")
        added = 0
        for box in soup.select("div.item_box"):
            a = box.select_one("p.item_name a")
            price_el = box.select_one("p.item_price")
            if not a or not price_el:
                continue
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            added += 1
            items.append({
                "raw_name": a.get_text(strip=True),
                "pid": m.group(1),
                "price": parse_price(price_el.get_text(" ", strip=True)),
                "product_url": f"{BASE_URL}?pid={m.group(1)}",
            })
        time.sleep(CRAWL_DELAY_SECONDS)
        if added == 0:
            break
    return items


def scrape_official_farms() -> dict[str, str]:
    """農園名(カタカナ) -> 国名(日本語)。"""
    soup = get(OFFICIAL_FARM_URL, "utf-8")
    lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n")]
    farms = {}
    for i, line in enumerate(lines):
        if line == "地域" and i + 1 < len(lines) and i >= 4:
            country_en = lines[i + 1].split("／")[0].strip().upper()
            # 並び: 英字名 / カタカナ名 / 生産者 / 氏名 / 地域 / 国
            kana = lines[i - 3] if lines[i - 2] == "生産者" else None
            if kana and country_en in COUNTRY_JA:
                farms[norm_key(kana)] = COUNTRY_JA[country_en]
    return farms


def scrape_official_lineup() -> dict[str, dict]:
    """公式 /onlineshop の現行ラインナップ。キー = norm_key(商品名部分)。"""
    soup = get(OFFICIAL_SHOP_URL, "utf-8")
    lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n")]
    lineup = {}
    for i, line in enumerate(lines):
        roast = None
        country = None
        title = None
        m = re.match(r"^(.+?)\s*[–-]\s*([A-Za-z ]+?)\s*/\s*(\S+)$", line)
        if m and lines[i - 1] and i >= 2:
            # シングル: 「カサ・ルミシタナ – Washed / エクアドル」
            title = f"{m.group(1)}-{m.group(2)}"
            country = m.group(3)
        else:
            m2 = re.match(r"^(\S+)\s*/\s*(.+ブレンド)$", line)
            if m2:
                title = m2.group(1)
        if not title:
            continue
        # コーヒーバッグ(6bag)のアソートは豆商品ではないので照合対象外
        if "6bag" in " ".join(lines[i + 1:i + 3]):
            continue
        # 直前数行に焙煎度ラベル
        for j in range(i - 1, max(i - 4, 0), -1):
            if lines[j] in ROAST_LABELS:
                roast = ROAST_LABELS[lines[j]]
                break
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        notes = nxt if nxt and not nxt.startswith("¥") and nxt != "Sold Out" else None
        tail = " ".join(lines[i + 1:i + 4])
        sold_out = "Sold Out" in tail.split("¥")[0]
        lineup[norm_key(title)] = {
            "roast": roast,
            "country": country,
            "notes": notes,
            "sold_out": sold_out,
        }
    return lineup


def representative_items(items: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """セット除外 → 銘柄ごとに最小重量を代表にする。"""
    non_bean, groups = [], {}
    for it in items:
        if any(kw in it["raw_name"] for kw in NON_BEAN_KEYWORDS):
            non_bean.append(it)
            continue
        it["weight_g"] = weight_g_from_name(it["raw_name"])
        groups.setdefault(norm_key(it["raw_name"]), []).append(it)
    reps, larger = [], []
    for key, lst in groups.items():
        lst.sort(key=lambda x: (x["weight_g"] is None, x["weight_g"] or 0))
        reps.append(lst[0])
        larger.extend(lst[1:])
    return reps, larger, non_bean


def build_record(it: dict, farms: dict, lineup: dict) -> dict:
    title = it["raw_name"]
    parsed = parse_product(title)
    key = norm_key(title)
    # ブレンドは「フユ / 冬限定ブレンド ( 150g )」→「フユ」で照合
    head = key.split("/")[0]
    off = lineup.get(key) or lineup.get(head)

    origin_country = parsed["origin_country"]
    origin_source = parsed["origin_source"]
    if not origin_country:
        for fk, country in farms.items():
            if key.startswith(fk):
                origin_country, origin_source = country, "公式農園一覧"
                break
    if off and off["country"] and not origin_country:
        origin_country, origin_source = off["country"], "公式ラインナップ"

    roast = parsed["roast_level"] or (off["roast"] if off else None)
    stock_status = "品切れ" if (off and off["sold_out"]) else detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": origin_country,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "flavor_notes": off["notes"] if off else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": it["product_url"],
    }


def scrape_all_products():
    items = scrape_list()
    farms = scrape_official_farms()
    time.sleep(CRAWL_DELAY_SECONDS)
    lineup = scrape_official_lineup()
    reps, larger, non_bean = representative_items(items)
    records, flavored = [], []
    for it in reps:
        rec = build_record(it, farms, lineup)
        if parse_product(it["raw_name"])["is_flavored"]:
            flavored.append(rec)
        else:
            records.append(rec)
    non_bean_records = [
        {"shop_name": SHOP_INFO["name"], "raw_name": n["raw_name"], "non_bean": True,
         "product_url": n["product_url"]} for n in non_bean
    ]
    larger_records = [
        {"shop_name": SHOP_INFO["name"], "raw_name": n["raw_name"], "larger_size": True,
         "product_url": n["product_url"]} for n in larger
    ]
    return records, flavored, non_bean_records, larger_records


if __name__ == "__main__":
    records, flavored, non_bean_records, larger_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored,
        "non_bean_products_excluded": non_bean_records,
        "larger_size_products_excluded": larger_records,
    }
    with open("data_kariomonscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kariomonscoffee.json に出力しました"
          f"(セット等{len(non_bean_records)}件、大容量{len(larger_records)}件を除外)")
