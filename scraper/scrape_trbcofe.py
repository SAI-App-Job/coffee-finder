# -*- coding: utf-8 -*-
"""
scrape_trbcofe.py

トレビアン珈琲(trb-cofe.com、埼玉県川越市鯨井新田16-47、直火式焙煎機による自家焙煎、
電話・FAX・メール注文で全国発送)の商品情報を取得する。WordPress上の1ページ構成で、
「COFFEE価格表」の見出し以降に商品が「商品名→説明→在庫(常時焙煎/注文焙煎/夏季限定)
→煎り方→税込価格 NET100g/200g/500g」の順で並ぶ。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): コーヒー豆38銘柄(ストレート・ブレンド・その他)。
水出しコーヒーバッグ(2種)は豆ではなくパック製品のため除外。代表重量は表示されている
最小サイズ(通常100g、「その他」の注文焙煎は200g、一部ブレンドは500gのみ)。
「夏季限定」(5月〜9月)のスペシャルアイス・ブレンドは10月時点で販売期間外のため完売扱い。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "トレビアン珈琲",
    "url": "http://trb-cofe.com/",
    "platform": "WordPress(電話・FAX・メール注文)",
    "address": "埼玉県川越市鯨井新田16-47",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "http://trb-cofe.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("水だし",)

# 銘柄名・説明から産地が判別できないもの(説明文の産地記載による)
ORIGIN_OVERRIDES = {
    "ブラジルサントス№2 M18": "ブラジル",
    "モカ シダモ Ｇ2Ｗ": "エチオピア",
    "グレートマウンテン": "ジャマイカ",
    "パナマSHB": "パナマ",
    "サンマリノ サンドライ 18M": "ブラジル",
    "エーデル ワイス AA（タンザニア）": "タンザニア",
    "ハイチ（Ｗ／ウォッシュド）": "ハイチ",
    "ブルンディ（Ｗ／ウォッシュド）": "ブルンディ",
    "ガヨマウンテン （インドネシア）": "インドネシア",
    "トラジャ ママサカロシ （インドネシア）": "インドネシア",
    "バリ アラビカW 神山（インドネシア）": "インドネシア",
    "モカマタリ（イエメン）": "イエメン",
    "クリスタル マウンテン（キューバ）": "キューバ",
    "ハワイコナ ファンシー": "アメリカ(ハワイ)",
    "ハイマウンテン （ジャマイカ）": "ジャマイカ",
    "インド プランテーションＡ": "インド",
    "ナリーニョ SP （コロンビア）": "コロンビア",
    "シグリ AA （パプアニューギニア）": "パプアニューギニア",
    "エルサルバドル （ブルボンSHG）": "エルサルバドル",
    "メキシコ アルチュラ": "メキシコ",
    "グァテマラ(カフェインレス)": "グアテマラ",
    "ペルー （W／ウォッシュド）": "ペルー",
}


HEADINGS = ("ストレート", "ブレンド", "その他", "? ?")


def parse_blocks(lines: list[str]) -> list[dict]:
    """価格表の行列を商品ブロックに分割する。

    1ブロック: 商品名 → 説明(1行以上) → 在庫 → 区分 → [煎り方 → 煎度] → (税込価格 → NETxg → 価格 → 円)×n
    """
    start = next(i for i, ln in enumerate(lines) if ln == "COFFEE価格表")
    end = next((i for i, ln in enumerate(lines) if i > start and ln.startswith("全国発送")), len(lines))
    body = lines[start + 1:end]

    blocks: list[dict] = []
    i = 0
    while i < len(body):
        pre: list[str] = []
        while i < len(body) and body[i] != "在庫":
            if body[i] not in HEADINGS:
                pre.append(body[i])
            i += 1
        if i >= len(body) or not pre:
            break
        name, desc_lines = pre[0], pre[1:]
        stock_kind = body[i + 1]
        k = i + 2
        roast = None
        prices: dict[int, int] = {}
        while k < len(body):
            if body[k] == "煎り方" and k + 1 < len(body):
                roast = body[k + 1]
                k += 2
                continue
            m = re.match(r"NET(\d+)g$", body[k])
            if m and k + 1 < len(body) and re.match(r"[\d,]+$", body[k + 1]):
                prices[int(m.group(1))] = int(body[k + 1].replace(",", ""))
                k += 3  # NETxg, 価格, 円
                continue
            if body[k] == "税込価格":
                k += 1
                continue
            break
        blocks.append({"name": name, "desc": " ".join(desc_lines), "stock_kind": stock_kind, "roast": roast, "prices": prices})
        i = k
    return blocks


ROAST_MAP = {
    "中煎り": "ハイロースト",
    "中煎り深": "シティロースト",
    "中煎り浅": "ミディアムロースト",
    "深煎り浅": "フルシティロースト",
    "深煎り": "フレンチロースト",
    "極深煎り": "イタリアンロースト",
}


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    records = []
    for b in parse_blocks(lines):
        name = b["name"]
        if any(k in name for k in EXCLUDE_KEYWORDS) or not b["prices"]:
            continue
        weight = min(b["prices"])
        price = b["prices"][weight]
        out_of_season = b["stock_kind"] == "夏季限定"
        is_blend = "ブレンド" in name

        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            override = ORIGIN_OVERRIDES.get(name)
            detected = override or detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)

        roast_raw = b["roast"]
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": ROAST_MAP.get(roast_raw) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": b["desc"] or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "完売" if out_of_season else "販売中",
            "out_of_stock": out_of_season,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 全商品が同一ページのため、商品IDを一意にするフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_trbcofe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_trbcofe.json に出力しました")


if __name__ == "__main__":
    main()
