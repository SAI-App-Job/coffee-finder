# -*- coding: utf-8 -*-
"""
scrape_coffeeclub.py

珈琲倶楽部(coffeeclub.co.jp、運営:珈琲問屋長澤、東京都東大和市中央4-1043-24、焙煎・販売。
東村山市栄町にも拠点があり計2拠点)の商品情報を取得する。「インターネット通販のみ。店舗では
行っていません」と明記された通販専門の自家焙煎店で、独自サイト+ショップメーカー(カート)。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧(/coffee/)の「コーヒー豆一覧」(現在販売中のコーヒー豆
約70種)を対象とする。ストレートとブレンドの区別は一覧の「ストレート」(/coffee/blend.php?sb=1)
「ブレンド」(/coffee/blend.php?sb=2)の分類に従う(ブラジル・サンバ(ブラジル産の特別ロットを
ブレンドしたと説明)・希望の香り・未来日記・武蔵野日記等はブレンド側に分類されている)。
一覧には焙煎豆のみで、注文時に「生豆のまま」を選べるオプションがあるが、商品自体は焙煎豆。
カシューナッツ(detail_kanren.php?cn=202)・ドリップパック・プレミアム(別ページ)・生豆一覧は対象外。

【重量・価格】
各商品の100g/200g/300g/500g/1kgの表のうち最小の100gの税込価格(一覧表の1列目)。
焙煎度は受注焙煎で、注文時に「ライト〜フレンチ」から選べる(お勧めの焙煎度を一覧に表示)。
お勧め焙煎度を roast_hint に保持し、roast_levelは「ハイ(中炒り)」等のキーワードから
推定せずお勧め焙煎度の表記から取る。産地は一覧の「原産地」欄をまず使い、名前に国名がある
ときは名前を優先する(「ハイチ・フレンチブルー」は原産地欄が「コスタリカ」と記載されているが、
商品名のハイチを採用)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import ROAST_KEYWORDS, apply_category_hint_fallback, detect_country_name, parse_product

SHOP_INFO = {
    "name": "珈琲倶楽部",
    "url": "https://www.coffeeclub.co.jp/",
    "platform": "ショップメーカー(独自サイト)",
    "address": "東京都東大和市中央4-1043-24",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.coffeeclub.co.jp"
LIST_URL = f"{BASE_URL}/coffee/"
BLEND_URL = f"{BASE_URL}/coffee/blend.php?sb=2"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ORIGIN_FIELD_OVERRIDES = {
    "パプア・ニューギニア": "パプアニューギニア",
    "米国": "アメリカ(ハワイ)",
    "ハワイ島": "アメリカ(ハワイ)",
    "インド": "インド",
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def cn_from_href(href: str) -> str | None:
    m = re.search(r"cn=(\d+)", href)
    return m.group(1) if m else None


def blend_ids() -> set[str]:
    soup = BeautifulSoup(fetch(BLEND_URL), "html.parser")
    ids = set()
    for a in soup.select("ul.coffee_list h4 a"):
        cn = cn_from_href(a["href"])
        if cn:
            ids.add(cn)
    return ids


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items = []
    seen = set()
    for li in soup.select("ul.coffee_list > li"):
        a = li.select_one("h4 a")
        if not a:
            continue
        cn = cn_from_href(a["href"])
        if not cn or cn in seen:
            continue
        seen.add(cn)
        name = re.sub(r"^\s*\d+\s*", "", re.sub(r"\s+", " ", a.get_text(" ", strip=True))).strip()
        gensan = li.select_one(".gensan")
        origin_field = re.sub(r"^原産地[：:]", "", gensan.get_text(strip=True)) if gensan else None
        rec = li.select_one(".innerR p")
        roast_hint = re.sub(r"^オススメ焙煎[：:]", "", rec.get_text(strip=True)) if rec else None
        ths = [t.get_text(strip=True) for t in li.select("table th")]
        tds = [t.get_text(strip=True) for t in li.select("table td")]
        weight_g = price = None
        if ths and tds:
            wm = re.match(r"^(\d+)\s*g$", unicodedata.normalize("NFKC", ths[0]), re.I)
            pm = re.search(r"([\d,]+)\s*円", tds[0])
            if wm and pm:
                weight_g = int(wm.group(1))
                price = int(pm.group(1).replace(",", ""))
        com = li.select_one(".s_com")
        desc = re.sub(r"[.…。]{2,}$", "", com.get_text(strip=True)).strip() if com else None
        items.append({
            "cn": cn,
            "name": name,
            "origin_field": origin_field,
            "roast_hint": roast_hint,
            "weight_g": weight_g,
            "price": price,
            "desc": desc,
        })
    return items


def roast_level_from_hint(hint: str | None) -> str | None:
    if not hint:
        return None
    head = hint.split("（")[0].strip()
    for kw, roast in ROAST_KEYWORDS.items():
        if head == kw:
            return roast
    return None


def build_record(item: dict, blends: set[str]) -> dict | None:
    name = unicodedata.normalize("NFKC", item["name"]).replace("(R)", "").strip()
    name = re.sub(r"\s+", " ", name)
    parsed = parse_product(name)
    if item["cn"] in blends or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            of = item["origin_field"] or ""
            of_norm = unicodedata.normalize("NFKC", of)
            country = next((c for k, c in ORIGIN_FIELD_OVERRIDES.items() if k in of_norm and k != "インド"), None)
            country = country or detect_country_name(of_norm)
            if not country and "インド" in of_norm and "インドネシア" not in of_norm:
                country = "インド"
            if not country and "バリ" in of_norm:
                country = "インドネシア"
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "origin_field"
        if "ハワイ" in name or "ハワイ" in unicodedata.normalize("NFKC", item["origin_field"] or ""):
            parsed["origin_country"] = "アメリカ(ハワイ)"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level_from_hint(item["roast_hint"]) or parsed["roast_level"],
        "roast_hint": (
            "お勧め焙煎度: " + item["roast_hint"] + "(注文時にライト〜フレンチから選択)"
            if item["roast_hint"] and item["roast_hint"] != "オススメ"
            else "注文時に焙煎度(ライト〜フレンチ)を選択(受注焙煎)"
        ),
        "flavor_notes": item["desc"] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{BASE_URL}/coffee/detail.php?cn={item['cn']}",
    }


def scrape_all_products() -> list[dict]:
    blends = blend_ids()
    records = []
    for item in list_items():
        rec = build_record(item, blends)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeeclub.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeclub.json に出力しました")


if __name__ == "__main__":
    main()
