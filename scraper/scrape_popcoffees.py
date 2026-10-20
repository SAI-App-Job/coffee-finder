# -*- coding: utf-8 -*-
"""
scrape_popcoffees.py

POPCOFFEES(POPLIFE CO.、福岡県福岡市東区美和台4-6-2、popcoffees.com)の商品情報を取得する。
有機無農薬・フェアトレードコーヒー専門の自社焙煎。WordPress + Welcart(UTF-8)。

【実店舗・自家焙煎の根拠(2026-10-20確認)】
 - 公式 CAFEページ(popcoffees.com/shopinfo/): 「POPCOFFEES CAFE」「自社焙煎工場を併設」、所在地 福岡県福岡市東区美和台4-6-2、
   TEL 092-605-0155、営業 9:30～18:00 月曜定休、西鉄貝塚線三苫駅から徒歩2分、「コーヒー豆も全種販売しています」。
 - 公式 BEANSページ(popcoffees.com/beans/): 焙煎機(ディードリッヒ、ローストマスター YAZAWA)。
 - トップページ: 「焙煎は自社の有機JAS認定工場で行ないます」。

【対象商品について】
カテゴリ STRAIGHT・BLEND の豆の単品(各200g、豆のまま/細挽き/中挽き/粗挽きを選択)。クリックポスト・レターパックの
100g×3袋選択、1kg(200g×5)大容量、ギフト、ドリップパック、水出し、インスタント、リキッド、紅茶、カフェラテベースは除外。
エチオピアNo.1グレードの専用ページ(slug=organic)は浅煎り・中深煎りの200g単品(各1,800円、現在売り切れ)の2件を収録し、
400g(200g×2袋)のセット売りは除外した。
商品ページは Welcart の `.field_price`(販売価格・税込)と「在庫状態」で価格・在庫を判定する。
"""

import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "POPCOFFEES",
    "url": "https://popcoffees.com/",
    "platform": "Welcart(WordPress)",
    "address": "福岡県福岡市東区美和台4-6-2",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。/press/wp-admin/ のみDisallow)",
    "source_note": "公式サイト(https://popcoffees.com/)のカテゴリ STRAIGHT・BLEND の各商品ページを2026-10-20に確認。"
                   "住所と自社焙煎工場併設は公式CAFEページ(/shopinfo/)の記載",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://popcoffees.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 2

# (slug, 商品名, 産地(Noneは不明/ブレンド), ブレンドか, 焙煎度)
ITEMS = [
    ("kil", "オーガニック・キリマンジャロ", "タンザニア", False, None),
    ("organic-peru-200g", "オーガニック・ペルー", "ペルー", False, "浅煎り"),  # 説明文「焙煎度：Light Roast」
    ("pop00014", "オーガニック・コロンビア", "コロンビア", False, None),
    ("pop00013", "オーガニック・エチオピア", "エチオピア", False, None),
    ("pop00012", "オーガニック・グアテマラ", "グアテマラ", False, None),
    ("pop00011", "オーガニック・ブラジル", "ブラジル", False, None),
    ("pop00010", "オーガニック・マンデリン", "インドネシア", False, "深煎り"),
    ("pop00009", "オーガニック・メキシコ", "メキシコ", False, None),
    ("pop00008", "オーガニック・ウガンダ", "ウガンダ", False, "深煎り"),
    ("pop00007", "オーガニック・東ティモール", "東ティモール", False, "中深煎り"),
    ("pop00016", "有機カフェインレスコーヒー", None, False, "中深煎り"),
    ("mitoma", "ミトマビーチブレンド", None, True, None),
    ("pop0006", "季節のブレンド", None, True, None),
    ("p00005", "オールドクラシック ブレンド", None, True, None),
    ("pop00004", "ラテンビート ブレンド", None, True, None),
    ("pop00003", "ポップコーヒーズハウス ブレンド", None, True, None),
    ("pop00002", "ブルース オブ アメリカン ブレンド", None, True, None),
    ("pop00001", "ニューオリンズジャズ ブレンド", None, True, None),
]
# 複数SKUページ(エチオピアNo.1グレード): (SKU番号, 商品名, 焙煎度)
ETHIOPIA_G1_URL = f"{BASE_URL}/organic/"
ETHIOPIA_G1 = [
    ("pop00033-01", "オーガニック エチオピアG1 ナチュラル 浅煎り", "浅煎り"),
    ("pop00033-03", "オーガニック エチオピアG1 ナチュラル 中深煎り", "中深煎り"),
]


def get_soup(url):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content.decode("utf-8"), "html.parser")


def page_info(soup):
    text = soup.get_text("\n", strip=True)
    stock = re.search(r"在庫状態 : (\S+)", text)
    price = soup.select_one(".field_price")
    pm = re.search(r"¥([\d,]+)", price.get_text()) if price else None
    i, j = text.find("在庫状態"), text.find("オプションを指定")
    lines = [l for l in text[i:j].split("\n")[1:] if l.strip() and not l.startswith(("●", "<"))]
    return {
        "price": int(pm.group(1).replace(",", "")) if pm else None,
        "sold_out": bool(stock) and stock.group(1) != "在庫有り",
        "desc": lines[0][:200] if lines else None,
    }


def make_record(name, url, price, weight, origin, blend, roast, sold_out, desc, processing=None):
    parsed = parse_product(name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin and origin in name else ("description" if origin else None)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,  # 商品名の語(「ハウス」等)からの誤検出を避け、ページに明記のものだけ
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products():
    records = []
    for slug, name, origin, blend, roast in ITEMS:
        time.sleep(CRAWL_DELAY_SECONDS)
        url = f"{BASE_URL}/{slug}/"
        info = page_info(get_soup(url))
        if info["price"] is None:
            print(f"[warn] 価格取得失敗: {slug}")
            continue
        records.append(make_record(name, url, info["price"], 200, origin, blend, roast, info["sold_out"], info["desc"]))
    time.sleep(CRAWL_DELAY_SECONDS)
    soup = get_soup(ETHIOPIA_G1_URL)
    desc = "ベリー系アロマ、魅惑のハーモニー！ありそうでなかった希少オーガニック モカ"
    rows = soup.select("table.skumulti tbody > tr")
    for idx, tr in enumerate(rows):
        sku = tr.get_text(" ", strip=True).split(" ")[0]
        for code, name, roast in ETHIOPIA_G1:
            if sku == code:
                # SKUは2行構成(1行目: 名称・価格、2行目: 在庫状態・数量)。価格は「(定価) 販売価格」の販売価格(最後の値)
                text = tr.get_text(" ", strip=True)
                nums = re.findall(r"¥([\d,]+)", text)
                price = int(nums[-1].replace(",", "")) if nums else None
                sold_out = "売り切れ" in rows[idx + 1].get_text(" ", strip=True) if idx + 1 < len(rows) else "売り切れ" in text
                records.append(make_record(name, f"{ETHIOPIA_G1_URL}#{quote(name)}", price, 200, "エチオピア", False, roast, sold_out, desc, processing="ナチュラル"))
    return records


def main():
    records = scrape_all_products()
    with open("data_popcoffees.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_popcoffees.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
