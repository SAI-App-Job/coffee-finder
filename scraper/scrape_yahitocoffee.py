# -*- coding: utf-8 -*-
"""
scrape_yahitocoffee.py

自家焙煎ヤヒトコーヒー(yahitocoffee.com、愛知県豊橋市西小鷹野4-6-2)のオンラインショップ
(ウェブショッピング)の商品情報を取得する。Jimdo Shop。

【対象商品について】
実データ確認済み(2026-10時点): オンラインショップ1ページ(/ウェブショッピング/)に全商品が
`div.j-product`ブロックとして並ぶ(14ブロック)。そのうち焙煎豆の12商品(シングルオリジン
8・デカフェ1・オリジナルブレンド3)を対象とし、「水出しコーヒーパック」「オリジナル
ドリップバッグ」は除外。各豆は200g(容量表記【容量】200g)のみの1サイズ販売で、
挽き方の選択肢(豆のまま/細挽き/中挽き/粗挽き)による価格差はない。
商品個別ページはなく、product_urlはショップページURL + 「#」 + ブロックid(例:#cc-m-14240198090)とする。

【在庫について】
在庫数表示(「在庫あり」)は一部の商品にしか出ないため、「カートに追加」ボタンが
あれば販売中、なければ完売とする(取得時点で12商品とも販売中)。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "ヤヒトコーヒー",
    "url": "https://yahitocoffee.com/",
    "platform": "Jimdo Shop",
    "address": "愛知県豊橋市西小鷹野4-6-2",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://yahitocoffee.com"
SHOP_PAGE = f"{BASE_URL}/{urllib.parse.quote('ウェブショッピング')}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_WORDS = ("水出し", "ドリップバッグ", "セット")
ROAST_JA = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り|中煎)")
ROAST_EN = re.compile(r"(フルシティ|ミディアム|ハイ|シティ|フレンチ|イタリアン|ライト|シナモン)")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def roast_of(text: str) -> str | None:
    compact = text.replace(" ", "")
    m = ROAST_JA.search(compact)
    if not m:
        return None
    ja = m.group(1)
    if ja == "中煎":
        ja = "中煎り"
    e = ROAST_EN.search(compact)
    if e:
        return f"{ja}({e.group(1)}ロースト)"
    return ja


def field(text: str, label: str) -> str | None:
    m = re.search(r"【" + label + r"】\s*(.+?)(?=\s*【|\s*$)", text, re.S)
    return m.group(1).strip() if m else None


def scrape_all_products() -> list[dict]:
    resp = requests.get(SHOP_PAGE, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for block in soup.select("div.j-product"):
        raw_lines = [ln.strip() for ln in block.get_text("\n", strip=True).split("\n") if ln.strip()]
        if not raw_lines:
            continue
        name = norm(raw_lines[0])
        if any(w in name for w in EXCLUDE_WORDS):
            continue
        text = norm(" ".join(raw_lines))

        wm = re.search(r"【容 ?量】\s*(\d+)\s*g", text)
        if not wm:
            continue
        weight = int(wm.group(1))
        pm = re.search(r"[￥¥]([\d,]+)\s*税込", text)
        price = int(pm.group(1).replace(",", "")) if pm else None
        rm = re.search(r"【焙煎度】\s*(.{0,30})", text)
        roast = roast_of(rm.group(1)) if rm else None
        pr = re.search(r"【精製方法】\s*(.{0,30})", text)
        process = pr.group(1) if pr else None
        variety = None
        norm_lines = [norm(ln) for ln in raw_lines]
        for ln in norm_lines:
            vm = re.match(r"【品 ?種】\s*(.+)$", ln)
            if vm:
                variety = vm.group(1).strip()
        # 説明文: 最後の【...】ラベル行より後〜「豆のまま」の手前の行
        label_idx = [i for i, ln in enumerate(norm_lines) if ln.startswith("【")]
        end_idx = next((i for i, ln in enumerate(norm_lines) if ln == "豆のまま"), len(norm_lines))
        flavor = " ".join(norm_lines[label_idx[-1] + 1:end_idx]).strip() or None if label_idx else None

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name.replace("グァテマラ", "グアテマラ"))
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"] or (detect_processing_method(process) if process else None)
        if "カフェインレス" in name:
            parsed["category"] = "ストレート"

        available = "カートに追加" in text
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": flavor,
            "farm_note": f"品種: {variety}" if variety else None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{SHOP_PAGE}#{block.get('id')}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yahitocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yahitocoffee.json に出力しました")


if __name__ == "__main__":
    main()
