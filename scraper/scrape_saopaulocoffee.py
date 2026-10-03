# -*- coding: utf-8 -*-
"""
scrape_saopaulocoffee.py

サンパウロコーヒー(saopaulocoffee.com、1979年創業、東京都大田区西蒲田7-52-5の蒲田店と
品川区南大井の大森店(焙煎所)の2店舗)の公式直販サイトの商品情報を取得する。創業時から
続く直火焙煎の自家焙煎店。MakeShop(新形式 /view/item/)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(/view/category/all_items)のうち、
焙煎済みコーヒー豆のみを対象とする。
 - ブレンド(ロイヤル・ファクトリーNo.88・アインシュペンナー・キリマンジャロ・モカ・
   ダークロースト・ほろにが・ブルーマウンテンNo.1ブレンド)
 - アイスコーヒー用の焙煎豆: 「マイルドアイスコーヒー」(配合の記載なし、ブレンド扱い・産地None)、
   「浅煎り・深煎りミックス モカマタリスペシャルアイス」(モカマタリ100%、同じ豆を浅煎りと
   深煎りで焙煎してアフターミックスしたものでイエメン産ストレート扱い)
 - ストレート・産地指定(グアテマラ・ペルー・マンデリン・モカマタリ・コロンビア・
   ブラジル・エチオピア2種・ケニア・コスタリカ・パプアニューギニア)
 - カフェインレス珈琲(180g。複数のデカフェ豆を独自に調合して直火焙煎する旨の記載のため
   ブレンド扱い・産地None)
除外: 生豆(「生豆」始まりの全商品。焙煎前の豆)・ドリップパック・ポーションコーヒー・
ダンクコーヒー・北海道名水PET・「ポストへお届けコーヒー便 選べる100g×3個」(複数銘柄の
詰合せ)。

【重量・価格】
商品詳細ページの「量目」セレクトの最小サイズ(通常200g。800g・3000gは別サイズ)と、
ページに表示される税込の基準価格(200g価格)を採用する。「モカブレンド」は200gに
「今月限定10％オフ(-167円)」が適用されているが、通常価格(表示価格1,804円)を採用した。
カフェインレス珈琲は商品名の「180g」を採用。

【在庫】
詳細ページのカートボタン領域にあるSOLD OUT表示(span.goods-cart-btn-nonactive)は
在庫ありの時は class="off" で隠されているため、"off"クラスが無ければ完売と判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "サンパウロコーヒー",
    "url": "https://saopaulocoffee.com/",
    "platform": "MakeShop",
    "address": "東京都大田区西蒲田7-52-5",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://saopaulocoffee.com"
LIST_URL = f"{BASE_URL}/view/category/all_items"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ("生豆", "ドリップ", "ポーション", "ダンク", "PET", "コーヒー便", "ケース", "器具", "フィルター")
ROAST_PATTERN = re.compile(r"(中深煎り|浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items: dict[str, dict] = {}
    for li in soup.select("li"):
        name_el = li.select_one("span.category-item-name")
        price_el = li.select_one("p.category-item-price")
        a = li.find("a", href=True)
        if not (name_el and price_el and a):
            continue
        m = re.search(r"/view/item/(\d+)", a["href"])
        pm = re.search(r"([\d,]+)", price_el.get_text())
        if not (m and pm):
            continue
        items.setdefault(m.group(1), {
            "id": m.group(1),
            "name": re.sub(r"\s+", " ", name_el.get_text(strip=True)).strip(),
            "price": int(pm.group(1).replace(",", "")),
        })
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    weight_g = None
    for sel in soup.select('select[data-id^="makeshop-item-option"]'):
        weights = []
        for opt in sel.select("option"):
            m = re.match(r"^\s*(\d+)\s*g", opt.get_text(strip=True))
            if m:
                weights.append(int(m.group(1)))
        if weights:
            weight_g = min(weights)
            break
    btn = soup.select_one("span.goods-cart-btn-nonactive")
    out_of_stock = bool(btn and "off" not in (btn.get("class") or []))
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    start = None
    for key in ("レビューを書く", "お買い物カートに入れる"):
        if key in lines:
            start = lines.index(key) + 1
            break
    desc_lines: list[str] = []
    if start is not None:
        for ln in lines[start:]:
            if "についてつぶやく" in ln or ln in ("シェアする", "お客様レビュー", "商品説明"):
                break
            if re.match(r"^(評価\d|\d(\.\d)?（\d+件）|レビュー)", ln) or len(ln) < 12:
                continue
            desc_lines.append(ln)
    return {"weight_g": weight_g, "out_of_stock": out_of_stock, "desc_lines": desc_lines}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    parsed = parse_product(name)
    is_blend = (
        "ブレンド" in name
        or name.startswith("マイルドアイスコーヒー")
        or "カフェインレス" in name
    )
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
    weight_g = detail["weight_g"]
    if weight_g is None:
        wm = re.search(r"(\d+)\s*g", name)
        weight_g = int(wm.group(1)) if wm else None
    desc = " ".join(detail["desc_lines"])
    flavor_notes = desc[:300] if desc else None
    rm = ROAST_PATTERN.search(desc)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": rm.group(1) if rm else None,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if detail["out_of_stock"] else "販売中",
        "out_of_stock": detail["out_of_stock"],
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/view/item/{item['id']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_saopaulocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_saopaulocoffee.json に出力しました")


if __name__ == "__main__":
    main()
