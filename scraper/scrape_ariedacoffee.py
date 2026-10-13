# -*- coding: utf-8 -*-
"""
scrape_ariedacoffee.py

自家焙煎 有枝珈琲(https://arieda-coffee.shop-pro.jp/、青森県八戸市南類家2丁目25-11)の商品情報を取得する。カラーミーショップ(shop-pro.jp系)。

【店舗発見の経緯】
全国再調査(青森県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 17商品のうちコーヒー豆9銘柄(シングルオリジン・ブレンド、100g/150g)を対象とする。ドリップバッグ・ディップタイプ・ギフトセット・飲み比べセット・1000g大容量(ブレンド08)は除外。旧BASEではなくカラーミーが現行ショップ。
商品一覧(?mode=srh&keyword=&sort=n)から商品ID(pid)を集め、各商品ページの
`var Colorme = {...}`(バリエーション・価格)と本文から情報を取得する。
商品名の重量表記(例: 「150g」)を重量とし、「豆のまま」(または「豆」)のバリエーションを代表とする。
文字コードはEUC-JP(実データ確認済み)。

【robots.txtについて】
確認済み(2026-10時点): User-agent: * は /secure/ と /cart/ のみ制限。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎 有枝珈琲",
    "url": "https://arieda-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "青森県八戸市南類家2丁目25-11",
    "prefecture": "青森県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://arieda-coffee.shop-pro.jp"
LIST_URL = BASE_URL + "/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# コーヒー豆以外(ドリップバッグ・ギフト・セット・飲料ベース・事業者向け大容量等)を除外するキーワード
NON_BEAN_KEYWORDS = ['ドリップバッグ', 'ディップタイプ', 'セット', '1000g']
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_KEYWORDS = ["中深煎り", "中浅煎り", "深煎り", "浅煎り", "中煎り"]
# 商品名・説明から産地を判定できない場合の明示(商品ID -> 国名)
ORIGIN_OVERRIDES = {}
# 説明文の取得方法: "between" = 「商品説明」〜「おすすめ商品」の間、"exp" = div.product_exp / 商品名直後の本文
DESC_MODE = "between"


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def extract_colorme(raw_html: str) -> dict:
    m = re.search(r"var\s+Colorme\s*=\s*", raw_html)
    if not m:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(raw_html[m.end():])
    except json.JSONDecodeError:
        return {}
    return data.get("product") or {}


def page_text(soup: BeautifulSoup) -> str:
    for x in soup(["script", "style"]):
        x.decompose()
    return re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))


def extract_description(soup: BeautifulSoup, text: str) -> str | None:
    desc = ""
    if DESC_MODE == "between":
        m = re.search(r"商品説明\s*(.*?)\s*(?:おすすめ商品|RECCOMEND)", text, re.S)
        desc = m.group(1) if m else ""
        desc = re.sub(r"【特徴の強さ】.*", "", desc, flags=re.S)
    else:
        exp = soup.select_one("div.product_exp")
        if exp:
            desc = exp.get_text(" ", strip=True)
        else:
            # 商品名・価格の直後〜「豆挽き」/「型番」の前の本文
            m = re.search(r"円\(内税\)\s*(.*?)\s*(?:豆挽き|型番)", text, re.S)
            if m:
                desc = m.group(1)
    desc = re.sub(r"\s+", " ", desc).strip().lstrip("# ").strip()
    return desc[:400] or None


def detect_sold_out(text: str) -> bool:
    idx = text.find("オプションの値段詳細")
    region = text[max(0, idx - 500): idx] if idx >= 0 else text[:2000]
    if re.search(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ", region, re.I):
        return True
    return "カートに入れる" not in region and "購入数" not in region


def pick_whole_bean_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    for v in variants:
        if (v.get("option1_value") or "").strip() in ("豆のまま", "豆"):
            return v
    return variants[0]


def scrape_all_products() -> list[dict]:
    resp = requests.get(LIST_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    pids = sorted(set(re.findall(r"pid=(\d+)", resp.text)))

    records = []
    for pid in pids:
        time.sleep(CRAWL_DELAY_SECONDS)
        url = f"{BASE_URL}/?pid={pid}"
        try:
            soup, raw = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        product = extract_colorme(raw)
        title = re.sub(r"\s+", " ", (product.get("name") or "")).strip()
        if not title:
            t = soup.find("title")
            title = re.sub(r"\s*-\s*[^-]*$", "", t.get_text()).strip() if t else ""
        if not title or any(k in title for k in NON_BEAN_KEYWORDS):
            continue
        variant = pick_whole_bean_variant(product.get("variants") or [])
        if not variant:
            continue
        price = variant.get("option_price_including_tax")
        wm = WEIGHT_PATTERN.search(title)
        weight = int(wm.group(1)) if wm else None

        text = page_text(soup)
        desc = extract_description(soup, text)
        sold_out = detect_sold_out(text)

        # 商品名の見出し語(【キャッチコピー】)を除いた名前
        name = re.sub(r"^【[^】]*】\s*", "", title).strip() or title
        parsed = parse_product(name)
        if "ブレンド" in title or "blend" in title.lower():
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["grade"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if pid in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
                parsed["origin_source"] = "raw_name"
        roast = parsed["roast_level"]
        if not roast:
            for kw in ROAST_KEYWORDS:
                if kw in name or (desc and kw in desc):
                    roast = kw
                    break
        if not roast and "深煎" in name:
            roast = "深煎り"
        if parsed["category"] != "ブレンド" and not parsed["processing_method"] and desc:
            # 商品名に精製方法が無い場合は説明文の表記から補う(例: 「ナチュラル精製」)
            parsed["processing_method"] = parse_product(desc)["processing_method"]

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(price) if price else None,
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ariedacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ariedacoffee.json に出力しました")


if __name__ == "__main__":
    main()
