# -*- coding: utf-8 -*-
"""
scrape_roastingcafe.py

珈琲豆焙煎工房 ROASTING CAFE(www.roastingcafe.jp、東京都大田区池上6-1-4、池上駅前の自家焙煎店)の
商品情報を取得する。おちゃのこネット(Ocnk、旧 roastingcafe.ocnk.net は www.roastingcafe.jp へ301転送)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品 /product-list(62件、1ページ)のうちコーヒー豆のブレンド・
シングル・デカフェ。除外: コーヒーギフトセット、お好み詰め合わせ用ラッピング、水出しアイスコーヒーパック、
器具(ペーパー・ドリッパー・サーバー)、価格未定の「イエメン ホワイトキャメル」(11月入荷予定)。
「プレミアム アイスブレンド」「アイスコーヒーブレンド」は焙煎豆のブレンドなので対象に含める。
【重量】店舗案内に「『1袋』は生豆240g焙煎して焙煎後約200gになったコーヒー豆/粉」とあるため、
全商品 weight_g=200(焙煎後の約表記)。価格は税込表示(軽減税率8%)。
【焙煎度】シングルは注文時に焙煎度(おまかせ/浅煎り〜極深煎り/生豆)を選ぶ方式のため roast_level=None・
roast_selectable=True。ブレンドは焙煎度の選択肢が無く、商品説明に「中煎りライトタイプ」等とある場合のみ
roast_levelに採用する。
【robots.txt】GPTBot等の特定UAのみDisallow(User-agent: * には制限なし)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "珈琲豆焙煎工房 ROASTING CAFE",
    "url": "https://www.roastingcafe.jp/",
    "platform": "おちゃのこネット",
    "address": "東京都大田区池上6-1-4",
    "prefecture": "東京都",
    "robots_txt_status": "許可(特定のAIクローラ名のみDisallow、User-agent: * は制限なし)",
    "source_note": "公式 https://www.roastingcafe.jp/page/2 (2026-10-20確認)に「この店舗内で焙煎して発送しています。勿論、店頭販売もしています」"
                   "「直火式小型ガス釜ロースターで、ご注文ごとに焙煎」。特商法表示 https://www.roastingcafe.jp/info も同住所。"
                   "商品一覧のコーヒー豆を収録。1袋は焙煎後約200g。お知らせ等の日付表示はなく更新時期は不明だが、"
                   "「2026 ハロウィン スペシャルブレンド」等2026年の商品が掲載されている。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://www.roastingcafe.jp"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
SLEEP = 2.0
BAG_WEIGHT_G = 200
EXCLUDE_NAMES = ["ギフト", "ラッピング", "水出し", "ペーパー", "ドリッパー", "サーバー", "ホワイトキャメル"]
ROAST_WORDS = [("極深煎り", "極深煎り"), ("中深煎り", "中深煎り"), ("深煎り", "深煎り"), ("中煎り", "中煎り"), ("浅煎り", "浅煎り")]


def get(url):
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_cells(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for li in soup.select("li.list_item_cell"):
        pid = li.select_one("[data-product-id]")["data-product-id"]
        name = re.sub(r"\s+", " ", li.select_one(".goods_name").get_text(" ", strip=True)).strip()
        price_el = li.select_one(".selling_price .figure")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        stock = li.select_one(".stock")
        out.append({
            "pid": pid, "name": name,
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "stock": stock.get_text(" ", strip=True) if stock else "",
        })
    return out


def scrape_all_products() -> list[dict]:
    items = list_cells(get(f"{BASE_URL}/product-list"))
    blend_ids = {c["pid"] for c in list_cells(get(f"{BASE_URL}/product-list/21"))}
    decaf_ids = {c["pid"] for c in list_cells(get(f"{BASE_URL}/product-list/25"))}
    # 豆のカテゴリ(ブレンド・カフェインレス・産地別5区分)に属する商品だけを対象にする
    bean_ids = set(blend_ids) | set(decaf_ids)
    for cid in (36, 37, 38, 23, 24):
        bean_ids |= {c["pid"] for c in list_cells(get(f"{BASE_URL}/product-list/{cid}"))}

    records = []
    for it in items:
        name = it["name"]
        if it["price"] is None or any(k in name for k in EXCLUDE_NAMES) or it["pid"] not in bean_ids:
            continue
        html_text = get(f"{BASE_URL}/product/{it['pid']}")
        soup = BeautifulSoup(html_text, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n", strip=True))
        i = text.find("お気に入り登録")
        j = text.find("ページトップへ")
        desc_raw = text[i + len("お気に入り登録"):j].strip() if i >= 0 and j > i else ""
        roast_options = "焙煎度" in text[:i if i >= 0 else len(text)]
        is_blend = it["pid"] in blend_ids or "ブレンド" in name
        decaf = it["pid"] in decaf_ids or "デカフェ" in name

        desc = re.sub(r"\s+", " ", desc_raw)[:400] or None
        clean = re.sub(r"\s+", " ", name.replace("　", " ")).strip()
        parsed = parse_product(clean)
        components = []
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(clean) or detect_country_name(desc_raw.split("\n")[0] if desc_raw else "")
                if not c:
                    m = re.search(r"生産国[：:\s]*(\S+)", desc_raw)
                    c = detect_country_name(m.group(1)) if m else None
                if not c:
                    c = detect_country_name(desc_raw)
                if not c:
                    m = re.search(r"生産地[：:]\s*(\S+)", desc_raw)
                    c = detect_country_name(m.group(1)) if m else None
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, clean)

        processing = parsed["processing_method"]
        if not is_blend and not processing:
            m = re.search(r"精製\s*([^\n]+)", desc_raw)
            if m:
                processing = detect_processing_method(m.group(1).strip())
            if not processing:
                processing = extract_from_description(desc_raw)["processing_method"]
                processing = detect_processing_method(processing) if processing else None
        if is_blend:
            processing = None

        roast_level = None
        roast_hint = None
        if not roast_options:
            first = desc_raw.split("\n")[0] if desc_raw else ""
            for word, level in ROAST_WORDS:
                if word in first:
                    roast_level = level
                    roast_hint = first[:40]
                    break
        if roast_level is None and roast_options:
            roast_hint = "注文時に焙煎度を選択(浅煎り〜極深煎り・おまかせ)"

        in_stock = "完売" not in it["stock"] and "在庫なし" not in it["stock"]
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": clean + ("" if not decaf or "デカフェ" in clean else "(デカフェ)"),
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_selectable": bool(roast_options),
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": components,
            "price": it["price"],
            "weight_g": BAG_WEIGHT_G,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": f"{BASE_URL}/product/{it['pid']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_roastingcafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roastingcafe.json に出力しました")


if __name__ == "__main__":
    main()
