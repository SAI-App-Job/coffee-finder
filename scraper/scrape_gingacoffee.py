# -*- coding: utf-8 -*-
"""
scrape_gingacoffee.py

銀河コーヒー(焙煎コーヒー豆 専門店、千葉県市川市真間・松戸市矢切の2店舗)の
カラーミーショップ(shop.ginga.coffee、独自ドメイン)の商品情報を取得する。

【販売先の採用理由】
同店は Yahoo!ショッピング(ginga-coffee)とAmazonにも出店しているが、豆の品目が最も揃っている
自社のカラーミーショップ(約50銘柄、150g/350g)を採用した(Yahoo!側は重複させない)。

【店舗】公式 https://ginga.coffee/shopinfo に「どちらの店舗も焙煎したて」「松戸矢切店は10kg焙煎機を
設置し、直売も」とあり、直売所2店(市川真間店・松戸矢切店)。住所は本店の市川真間店を採用。

【対象】カテゴリ「コーヒー豆(豆のまま、粉)」(cbid=2651781)の焙煎豆。
除外: お試しアソート(80g×3種のセット)、コーヒーチェリーティー(カスカラ、cbid=2673009)、
ドリップバッグ・水出しバッグ・カフェオレベース・生豆(別カテゴリ)。
【価格・重量】Colorme の variants から「豆のまま」を選び、重量は90g以上の最小(ナポレオン・
コピ・ルアック・中山農園には25〜50gの少量版があるが、少量試飲サイズより100g前後を優先する方針)。
【文字コード】EUC-JP。robots.txt: /secure/ と /cart/ のみ禁止(2026-10-26確認)。
"""

import html
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    ORIGIN_COUNTRY_KEYWORDS,
    REGION_TO_COUNTRY,
)

SHOP_INFO = {
    "name": "銀河コーヒー",
    "url": "https://shop.ginga.coffee/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "千葉県市川市真間1-15-20 真間ビル1F",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/のみDisallow)",
    "source_note": "カラーミーショップ(https://shop.ginga.coffee/)のカテゴリ「コーヒー豆(豆のまま、粉)」と各商品ページを"
                   "2026-10-26に確認。住所は公式店舗案内(https://ginga.coffee/shopinfo)の市川真間店(2号店は松戸市三矢小台4-3-7)。"
                   "150g(または90g以上の最小重量)の豆のまま価格を採用。セット・ドリップバッグ・生豆・カスカラは除外",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://shop.ginga.coffee/"
LIST_URL = BASE_URL + "?mode=cate&cbid=2651781&csid=0&sort=n"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2.0

EXCLUDE_NAME_KEYWORDS = ["お試しアソート", "セット", "ドリップバッグ", "ギフト", "生豆"]
BLEND_PIDS = {"191079652", "179761760", "177228564"}  # デビル ブレンド / 市川真間ブレンド / ハロウィンブレンド
MIN_WEIGHT_G = 90
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
WEIGHT_RE = re.compile(r"(\d+)\s*[gｇ]")
ROAST_BREADCRUMB_RE = re.compile(r"ロースト（焙煎具合）\s*>\s*([^\n]+)")
SOLD_OUT_RE = re.compile(r"売り切れ|SOLD ?OUT|品切れ|完売|在庫なし")

# 商品名・説明文から国名を引けない銘柄の産地(説明文を確認して手当て)
ORIGIN_OVERRIDES = {
    "172776275": "セントヘレナ",  # ナポレオン セントヘレナ島 バンブーヘッジ農園
    "171439016": "中国",  # 桃源郷 雲南 天空農園
    "155396786": "タイ",  # ブルームーン タイ王国チェンライ
    "162645435": "日本",  # Japan 珈琲 中山農園(国産 沖縄)
    "161803781": "アメリカ(ハワイ)",  # ハワイコナ
}

_last = [0.0]


def fetch(url: str) -> str:
    wait = REQUEST_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
    _last[0] = time.time()
    resp.raise_for_status()
    return resp.content.decode("euc-jp", "replace")


def list_product_ids() -> list[tuple[str, str]]:
    out = []
    page = 1
    while True:
        html_text = fetch(LIST_URL if page == 1 else f"{LIST_URL}&page={page}")
        found = re.findall(r'<a href="\?pid=(\d+)">([^<]*(?:<img[^>]*>)?[^<]*)</a>\s*</div>', html_text)
        if not found:
            break
        for pid, name in found:
            if pid not in [x[0] for x in out]:
                out.append((pid, re.sub(r"<[^>]+>", "", name).strip()))
        page += 1
    return out


def earliest_country(text: str) -> str | None:
    best = None
    for table in (ORIGIN_COUNTRY_KEYWORDS, REGION_TO_COUNTRY):
        for kw, country in table.items():
            i = text.find(kw)
            if i >= 0 and (best is None or i < best[0]):
                best = (i, country)
    return best[1] if best else None


def roast_label(breadcrumb: str | None, name: str) -> str | None:
    if breadcrumb:
        m = re.match(r"([^（(]+)", breadcrumb)
        if m:
            return m.group(1).strip()
    m = re.search(r"(極深煎り|やや深煎り|中深煎り|深煎り|中浅煎り|やや浅煎り|浅煎り|中煎り)", name)
    return m.group(1) if m else None


def pick_variant(variants: list[dict]) -> dict | None:
    beans = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    if not beans:
        return None

    def w(v):
        m = WEIGHT_RE.search(unicodedata.normalize("NFKC", v.get("option2_value") or ""))
        return int(m.group(1)) if m else None

    sized = [(w(v), v) for v in beans if w(v) is not None]
    big = [x for x in sized if x[0] >= MIN_WEIGHT_G] or sized
    if not big:
        return beans[0]
    return min(big, key=lambda x: x[0])[1]


def parse_detail(pid: str, list_name: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_RE.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1))["product"]
    name = html.unescape(product["name"]).strip()
    soup = BeautifulSoup(html_text, "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    text = soup.get_text("\n", strip=True)
    bc = ROAST_BREADCRUMB_RE.search(text)
    roast = roast_label(bc.group(1) if bc else None, name)

    # 説明文: 「ツイート」の次の行から「豆を挽きますか？」まで
    desc = ""
    if "ツイート" in text:
        body = text.split("ツイート", 1)[1].split("豆を挽きますか？", 1)[0]
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        desc = "\n".join(lines)
    first_line = desc.split("\n")[0] if desc else ""

    v = pick_variant(product.get("variants", []))
    if v is None:
        return None
    wm = WEIGHT_RE.search(unicodedata.normalize("NFKC", v.get("option2_value") or ""))
    weight = int(wm.group(1)) if wm else None
    price = v["option_price_including_tax"]

    parsed = parse_product(name)
    is_blend = pid in BLEND_PIDS
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            c = earliest_country(desc)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
    sold_out = bool(SOLD_OUT_RE.search(text))
    return {
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
        "flavor_notes": first_line[:200] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, list_name in list_product_ids():
        if any(k in list_name for k in EXCLUDE_NAME_KEYWORDS):
            print(f"[skip] {list_name[:30]}")
            continue
        try:
            rec = parse_detail(pid, list_name)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗 {pid}: {e}")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_gingacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gingacoffee.json に出力しました")


if __name__ == "__main__":
    main()
