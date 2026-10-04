# -*- coding: utf-8 -*-
"""
scrape_gandalfcoffee.py

GANDALF COFFEE(https://gandalf.thebase.in/、兵庫県西宮市門戸荘15-3)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(兵庫県)の新規発掘で発見。

【住所について】
/law ページはBASE株式会社の所在地(東京都港区六本木)の代理表示のため採用しない。店舗サイトの「ABOUT」に「創業30年の西宮市の小さな自家焙煎珈琲屋」とあり、地域情報サイト(shingakunet.com 西宮北口エリアのカフェ一覧)に「兵庫県西宮市門戸荘15-3」と記載があることを確認した(2026-10)。

【対象商品について】
実データ確認済み(2026-10時点、sitemap.xml上44商品): 豆は15銘柄(各100g)。同一銘柄が「単品ポスト」(クリックポスト)と「単品クロネコ」(宅配便)の2ページあるため、「単品ポスト」を代表として収録した。飲み比べ・まとめ買い・ギフト・頒布会・ドリップパック・水出しは除外。重量・焙煎度は説明文の「内容量」「焙煎度」欄から採用し、焙煎度の記載が無い銘柄はnull(キリマンジャロのみ説明文「中深に炒ってます」から中深煎り)。
商品名・重量・焙煎度は、商品ページ(商品名・説明文)の表記を確認したうえで下のITEMSに
明示している。価格・在庫(item_purchasability)・説明文は商品ページから実行時に取得する。
ITEMSにもEXCLUDED_IDSにも無い商品がsitemap.xmlに現れた場合は、新商品の可能性があるため
警告を表示する(自動では収録しない)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GANDALF COFFEE",
    "url": "https://gandalf.thebase.in/",
    "platform": "BASE",
    "address": "兵庫県西宮市門戸荘15-3",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://gandalf.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(商品名・説明文に明記があるものだけ。無ければNone))
ITEMS = [
    ('69409084', 'バリ神山', 100, None, '深煎り'),
    ('69411602', 'ケニア', 100, None, None),
    ('69411935', 'ルビーマウンテン', 100, None, None),
    ('69414124', 'Gandalfブレンド', 100, 'ブレンド', None),
    ('69414471', 'モカ・マタリ', 100, None, None),
    ('69415698', '季節のブレンド', 100, 'ブレンド', None),
    ('69440388', 'おもてなしブレンド', 100, 'ブレンド', None),
    ('69452301', 'セラード樹上完熟豆', 100, None, None),
    ('69507471', 'ガテマラ', 100, None, None),
    ('69853308', 'キリマンジャロ', 100, None, '中深煎り'),
    ('72395660', 'コロンビア', 100, None, '中深煎り'),
    ('72480268', 'コスタリカ', 100, None, '中煎り'),
    ('72480857', 'シグリ', 100, None, None),
    ('75277354', 'ペルー', 100, None, '深煎り'),
    ('76141023', 'モカ・ハラー', 100, None, '深煎り'),
]

# 豆以外(ドリップバッグ・セット・ギフト・定期便・器具・飲料・花・サンプル等)や、同一銘柄の
# 重複登録(重量違い・配送方法違い)のため収録しないsitemap上の商品ID
EXCLUDED_IDS = {'60892933', '59912990', '59554547', '26658369', '22269652', '59553759', '59554155', '59588263', '59636458', '63488218', '64483933', '67203314', '67205516', '69410972', '69411759', '69411987', '69414202', '69414554', '69415861', '69440439', '69452400', '69507598', '69853484', '72395800', '72480401', '75277085', '75277425', '76167566', '76842869'}

# coffee_parser.pyの国名辞書で検出できない/誤判定になる産地を明示する
ORIGIN_OVERRIDES = {'69409084': 'インドネシア', '69411935': 'ベトナム'}

# 説明文のうち、この文字列より後(送料・配送案内・注意書き等)はflavor_notesに含めない
DESC_CUT_MARKERS = ["＊豆のまま", "※お願い", "【送料", "-----", "北海道・沖縄へ", "【種類について】",
                    "焙煎日が限られて", "内容量", "ー・ー・", "■品名", "【賞味期限】", "※ハンドドリップ",
                    "【5,900円以上", "＊クリックポスト"]
# 説明文の先頭にある定型文(他ページへの誘導リンク・配送案内等)を取り除く正規表現
DESC_PREFIX_PATTERNS = [
    r"^(?:.*?https://www\.8coffee\.net/categories/\d+)+",
    r"^＊クリックポスト商品は400gまで同封できます。400gを超える場合はクロネコ商品をご選択ください。写真はイメージです。",
]
# 店舗全体の紹介文(商品固有の説明ではない)が入っている場合はflavor_notesにしない
DESC_GENERIC_PATTERNS = [r"自家焙煎\s*スペシャルティコーヒー.*LAKOTA", r"^Specialty coffeeのROAST"]

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one('[class*="item-detail_description"]')
    if el:
        text = el.get_text("\n")
    else:
        og = soup.select_one('meta[property="og:description"]')
        text = og.get("content", "") if og else ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    for pat in DESC_PREFIX_PATTERNS:
        text = re.sub(pat, "", text).strip()
    for pat in DESC_GENERIC_PATTERNS:
        if re.search(pat, text) and len(text) < 120:
            return None
    cut = len(text)
    for marker in DESC_CUT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            cut = min(cut, idx)
    text = text[:cut].strip()
    return text[:400] or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    desc = clean_description(soup)
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def check_new_items() -> None:
    """sitemap.xmlに未分類の商品があれば警告する(収録はしない)。"""
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] sitemap取得失敗 ({e})")
        return
    known = {item[0] for item in ITEMS} | set(EXCLUDED_IDS)
    for item_id in dict.fromkeys(re.findall(r"/items/(\d+)", resp.text)):
        if item_id not in known:
            print(f"[warn] 未分類の商品がsitemapにあります: {BASE_URL}/items/{item_id}")


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    check_new_items()
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_gandalfcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gandalfcoffee.json に出力しました")


if __name__ == "__main__":
    main()
