# -*- coding: utf-8 -*-
"""
scrape_tonegawacoffee.py

TONEGAWA COFFEE(自家焙煎コーヒー豆販売専門店、千葉県長生郡一宮町新地甲1921-10、beans-shop.com)の
商品情報を取得する。2002年開業の自家焙煎店で、店舗は1店のみ。eshop-do製の独自カート
(v5.eshop-do.com、ショップURLは beans-shop.com/esp/)。

【対象商品について】
実データ確認済み(2026-10時点): 「焙煎コーヒー豆MENU」(/esp/1-0-0/、2ページ)に、
ブレンド10種(01〜10番)とシングルオリジン9種の計19銘柄が並ぶ。「ギフトセレクション」
「コーヒーグッズ」「お試しセット」は別カテゴリのため対象外。

【価格・重量・在庫について】
商品詳細ページの価格は「豆のまま/200g」の税込価格(250gは+370〜390円の追加表記)で、
最小サイズの200gを代表重量とする(挽き方は選択式で価格は変わらない)。在庫は詳細ページの
「SOLD OUT」ボタン(class=sold_btn)の有無で判定する。商品名の末尾に付く「※完売」「※調整中」は
raw_nameから除去する(「※調整中」の01.爽やかSOFT BLENDはSOLD OUT表示のため完売扱い)。
焙煎度合は説明文の「焙煎度合〈09/10〉FrenchRoast」等の表記を roast_hint に保持し、
単一の焙煎度名(HighRoast/CityRoast/FrenchRoast等)の場合のみ roast_level に反映する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "TONEGAWA COFFEE",
    "url": "https://www.beans-shop.com/esp/",
    "platform": "独自カート(eshop-do)",
    "address": "千葉県長生郡一宮町新地甲1921-10",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.beans-shop.com"
LIST_URLS = [
    "https://www.beans-shop.com/esp/shop?p=1&cid=1",
    "https://www.beans-shop.com/esp/shop?p=2&cid=1",
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ギフト", "GIFT", "セット", "G600g")

# 商品名の英字国名から判別できないもの(綴り違い等)
ORIGIN_OVERRIDES = {
    "GUATEMARA": "グアテマラ",
    "TIMOR-LESTE": "東ティモール",
}
ROAST_MAP = {
    "LightRoast": "ライトロースト", "CinnamonRoast": "シナモンロースト",
    "MediumRoast": "ミディアムロースト", "HighRoast": "ハイロースト",
    "CityRoast": "シティロースト", "FullCityRoast": "フルシティロースト",
    "FrenchRoast": "フレンチロースト", "ItalianRoast": "イタリアンロースト",
}


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_product_urls() -> list[str]:
    urls: list[str] = []
    for lu in LIST_URLS:
        soup = fetch(lu)
        for a in soup.select("div.itemName a"):
            href = a.get("href", "")
            full = href if href.startswith("http") else BASE_URL + href
            if full not in urls:
                urls.append(full)
    return urls


def parse_detail(url: str) -> dict | None:
    soup = fetch(url)
    h2 = soup.select_one("h2.item-name_prd.pc_view") or soup.select_one("h2.item-name_prd")
    if not h2:
        return None
    raw = h2.get_text(strip=True)
    name = re.sub(r"※(完売|調整中)$", "", raw).strip()
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None

    price_el = soup.select_one("div.prd-price")
    pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
    sold = soup.select_one("input.sold_btn") is not None

    # 重量: 「豆のまま/200g」の最小値
    opt_text = soup.get_text("\n", strip=True)
    weights = [int(w) for w in re.findall(r"豆のまま/(\d+)g", opt_text)]
    weight = min(weights) if weights else None

    # 説明文
    desc_h = None
    for el in soup.find_all(string=re.compile(r"^商品説明$")):
        desc_h = el.parent
        break
    desc_lines: list[str] = []
    if desc_h is not None:
        body = desc_h.find_next(string=True)
        container = desc_h.find_parent()
        node = container.find_next_sibling() if container else None
        text = node.get_text("\n", strip=True) if node else ""
        desc_lines = [ln for ln in text.split("\n") if ln.strip()]
    if not desc_lines:
        m = re.search(r"商品説明\n(.*?)\n\[商品コード", opt_text, re.S)
        desc_lines = m.group(1).split("\n") if m else []

    roast_lines = [ln.strip() for ln in desc_lines[:6] if re.search(r"焙煎度合|焙煎の度合い|Roast", ln)]
    roast_hint = " / ".join(roast_lines) or None
    roast_level = None
    found = re.findall(r"(Light|Cinnamon|Medium|High|FullCity|City|French|Italian)Roast", roast_hint or "")
    if len(set(found)) == 1 and "&" not in (roast_hint or ""):
        roast_level = ROAST_MAP.get(found[0] + "Roast")
    notes = []
    farm = []
    process_text = ""
    for ln in desc_lines:
        if ln.startswith("◆") and "豆量" not in ln:
            notes.append(ln.lstrip("◆").strip())
        if re.match(r"(農園|所在|標高|品種|生産者|所有|銘柄|クロップ|規格)：", ln):
            farm.append(ln.strip())
        if re.match(r"精製", ln):
            process_text = ln
            farm.append(ln.strip())

    return {
        "name": name,
        "url": url,
        "price": int(pm.group(1).replace(",", "")) if pm else None,
        "weight_g": weight,
        "sold": sold,
        "roast_hint": roast_hint,
        "roast_level": roast_level,
        "notes": " ".join(notes) or None,
        "farm": " / ".join(farm) or None,
        "process_text": process_text,
    }


def build_record(d: dict) -> dict:
    name = d["name"]
    is_blend = "BLEND" in name.upper() or "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            prefix = name.split("/")[0].strip().upper()
            c = ORIGIN_OVERRIDES.get(prefix) or detect_country_name(prefix)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    processing = parsed["processing_method"] or detect_processing_method(d["process_text"])
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": d["roast_level"],
        "roast_hint": d["roast_hint"],
        "flavor_notes": d["notes"],
        "farm_note": d["farm"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": d["price"],
        "weight_g": d["weight_g"],
        "stock_status": "完売" if d["sold"] else "販売中",
        "out_of_stock": d["sold"],
        "product_url": d["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            d = parse_detail(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {url} ({e})")
            continue
        if d is None or d["price"] is None:
            continue
        records.append(build_record(d))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tonegawacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tonegawacoffee.json に出力しました")


if __name__ == "__main__":
    main()
