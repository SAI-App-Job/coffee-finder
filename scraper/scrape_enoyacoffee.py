# -*- coding: utf-8 -*-
"""
scrape_enoyacoffee.py

善福寺珈琲江ノ屋(enoyacoffee.tokyo、東京都杉並区善福寺2-18-1、大坂屋大塚商店の店内にある
5kg半熱風式焙煎釜による自家焙煎店・1店舗)のオンラインストアの商品情報を取得する。
WordPress + Welcart(UTF-8)。

【住所について】
特定商取引法に基づく表記(/trading.html)の事業者所在地「東京都杉並区善福寺2-18-1」を採用(2026-10確認)。

【対象商品について】
実データ確認済み(2026-10時点): オンラインストア(/shop/)のカテゴリ「国で選ぶ」「オリジナル
ブレンド」「カフェインレス」「コスタリカ」「ニカラグァ」「ブラジル」「焙煎度で選ぶ(浅煎り〜
深煎り)」の和集合のうち、焙煎済み豆の商品のみを収録する。水出珈琲パック・ドリップバッグの
飲み比べセット・珈琲缶セット・Simplifyドリッパーセット・グッズ(Tシャツ等)・
在庫状態「廃盤」の商品(江ノ屋オリジナル)は除外。
2026-10時点で在庫ありは3件のみ(パライネマ・Classico del Nord・ビターブレンド)で、
残り約22件は「売り切れ」(完売)として掲載されている。

【重量・価格・在庫】
重量は詳細ページのサイズ選択肢(100g/200g)の最小=100gを採用。価格は現在価格
(取消線の通常価格 .field_cprice ではなく、その後ろの表示価格)で、100g価格。
在庫は「在庫状態」表示(在庫有り/売り切れ)で判定。焙煎度は詳細ページ見出しの
「MEDIUM(浅煎り)」等から取得する(ミディアム/シティ/フルシティ/フレンチ)。
"""

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "善福寺珈琲江ノ屋",
    "url": "https://www.enoyacoffee.tokyo/shop/",
    "platform": "WordPress + Welcart",
    "address": "東京都杉並区善福寺2-18-1",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

SHOP_URL = "https://www.enoyacoffee.tokyo/shop/"
CATEGORY_IDS = [8, 32, 33, 34, 38, 29, 66, 67, 68, 69]
# 国別カテゴリ(ブレンドは対象外。商品の記載から国が判明しない場合のみのフォールバック)
CATEGORY_COUNTRY = {34: "コスタリカ", 38: "ニカラグア", 29: "ブラジル"}
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "パック", "珈琲缶", "ドリッパー", "Dripper", "ドリップバッグ", "Tシャツ", "Cap", "T サイズ", "手ぬぐい")
ROAST_MAP = [
    (re.compile(r"FULL\s*CITY", re.I), "フルシティロースト"),
    (re.compile(r"CITY", re.I), "シティロースト"),
    (re.compile(r"MEDIUM", re.I), "ミディアムロースト"),
    (re.compile(r"FRENCH", re.I), "フレンチロースト"),
]


def fetch(url: str) -> str | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat in CATEGORY_IDS:
        for page in range(1, 6):
            url = f"{SHOP_URL}?cat={cat}" + ("" if page == 1 else f"&paged={page}")
            html_text = fetch(url)
            if html_text is None:
                break
            soup = BeautifulSoup(html_text, "html.parser")
            new = 0
            for a in soup.select('a[href*="?p="]'):
                m = re.search(r"\?p=(\d+)", a["href"])
                if not m or int(m.group(1)) == 1064:  # 1064は送料・決済方法の案内ページ
                    continue
                entry = items.setdefault(m.group(1), {"id": m.group(1), "name": None, "cats": set()})
                entry["cats"].add(cat)
                text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                # 「SOLD OUT」は画像側リンクのバッジなので、名前付きのリンクだけを商品名に使う
                if text and text != "SOLD OUT" and entry["name"] is None:
                    entry["name"] = text
                    new += 1
            if new == 0:
                break
    return [v for v in items.values() if v["name"]]


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    h1 = soup.select_one("h1.item_page_title")
    title = h1.get_text(" ", strip=True) if h1 else ""
    fp = soup.select_one(".field_price")
    price = None
    if fp:
        nums = [int(x.replace(",", "")) for x in re.findall(r"¥\s*([\d,]+)", fp.get_text(" ", strip=True))]
        if nums:
            price = nums[-1]
    z = soup.select_one(".zaikostatus")
    zaiko = z.get_text(strip=True) if z else ""
    weight_g = None
    for dd in soup.select("dl.item-option dd"):
        t = dd.get_text(" ", strip=True)
        if "g" in t and re.match(r"^\s*\d+", t):
            weight_g = int(re.match(r"^\s*(\d+)", t).group(1))
            break
    body = soup.select_one(".post_content, .itemsubtitle, #itempage, .item-description")
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    desc = ""
    if "商品詳細" in lines:
        start = lines.index("商品詳細") + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith(("レビュー", "ログインしてレビュー"))), len(lines))
        # 英語訳以降・抽出レシピは除外し、日本語の紹介文のみを使う
        jp = []
        for ln in lines[start:end]:
            if ln.startswith(("“", "■", "This ", "Medium", "Light", "For ")):
                break
            jp.append(ln)
        desc = " ".join(jp)
    return {"title": title, "price": price, "zaiko": zaiko, "weight_g": weight_g, "desc": desc, "has_body": body is not None}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS) or any(kw in detail["title"] for kw in EXCLUDE_KEYWORDS):
        return None
    if "廃盤" in detail["zaiko"] or detail["price"] is None:
        return None
    out_of_stock = "売り切れ" in detail["zaiko"]
    title = detail["title"]
    parsed = parse_product(name)
    is_blend = "ブレンド" in name or "blend" in name.lower() or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            country = detect_country_name(title) or detect_country_name(detail["desc"][:150])
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description"
        if not parsed["origin_country"]:
            for cat in sorted(item["cats"]):
                if cat in CATEGORY_COUNTRY:
                    parsed["origin_country"] = CATEGORY_COUNTRY[cat]
                    parsed["origin_source"] = "category_hint"
                    break
    roast_level = None
    roast_hint = None
    rm = re.search(r"/\s*([A-Za-z\s+]+[（(][^）)]*[）)])\s*$", title)
    if rm:
        roast_hint = re.sub(r"\s+", " ", rm.group(1)).strip()
        for pat, label in ROAST_MAP:
            if pat.search(roast_hint):
                roast_level = label
                break
    processing = parsed["processing_method"] or detect_processing_method(name + " " + title)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": detail["desc"][:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": f"{SHOP_URL}?p={item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in sorted(list_items(), key=lambda x: int(x["id"])):
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            page_html = fetch(f"{SHOP_URL}?p={item['id']}")
            if page_html is None:
                continue
            detail = parse_detail(page_html)
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
    with open("data_enoyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_enoyacoffee.json に出力しました")


if __name__ == "__main__":
    main()
