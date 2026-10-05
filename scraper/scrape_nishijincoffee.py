# -*- coding: utf-8 -*-
"""
scrape_nishijincoffee.py

京都西陣珈琲(www.rakuten.co.jp/kn-coffee、京都府京都市上京区泰童片原町663-4、運営は
有限会社UP'S、焙煎者 牧野和喜)の楽天市場店の商品情報を取得する。
楽天市場(item.rakuten.co.jp、UTF-8)。

【取得方法】
楽天市場のrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止で、店舗カテゴリ・商品ページは
通常のGETで取得できる。カテゴリページ(item.rakuten.co.jp/kn-coffee/c/<cid>/、2ページ目以降は
/c/<cid>/<n>/)から商品コードを集め、各商品ページの itemprop="price"(税込)・
itemprop="availability"・title・説明文(span.sale_desc)を読む。サーバーが遅いため
リクエスト間隔を空け、取得に時間がかかる。削除済み商品コード(404)は読み飛ばす。

【対象商品について】
同一銘柄が200g・300g・400g・2kg等の別商品として並ぶため、銘柄(説明文の「商品名:」、
無ければ商品名の【】内)ごとに最小重量の商品を代表とする。重量は説明文の「内容量」
(「100gx2袋 合計200g」は合計)、無ければ商品名中のg/kg表記。内容量が不明な商品は除外
(オールドタイム3袋セット等)。除外: セット・詰め合わせ・飲み比べ・お試し・ドリップ・
水出しパック・袋/ラッピング等。価格は税込で、メール便送料無料の商品が多い(送料込みの価格)。

【焙煎度について】
多くの商品が「選べる焙煎(中煎り/深煎り)」で、商品名に複数の焙煎度が並ぶ場合は
roast_selectable=True・roast_level=null・roast_hintに表記を保持する。商品名に焙煎度が
1つだけの場合はroast_levelとする。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "京都西陣珈琲",
    "url": "https://www.rakuten.co.jp/kn-coffee/",
    "platform": "楽天市場",
    "address": "京都府京都市上京区泰童片原町663-4",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "kn-coffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/" + "{cid}/"
CATEGORY_IDS = ["0000000145", "0000000130", "0000000172", "0000000105", "0000000168"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.5
EXCLUDE_KEYWORDS = ("セット", "詰め合わせ", "詰合せ", "飲み比べ", "お試し", "ドリップバッグ", "ドリップバック",
                    "水出し", "手提げ", "ラッピング", "ギフト", "福袋", "パックセット")

COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
UNIT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|キログラム|キロ|g|k)(?![a-z])", re.I)


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def list_codes() -> list[str]:
    codes: list[str] = []
    for cid in CATEGORY_IDS:
        seen = set()
        for page in range(1, 10):
            url = CATEGORY_URL.format(cid=cid) + ("" if page == 1 else f"{page}/")
            resp = fetch(url)
            if resp.status_code != 200:
                break
            page_codes = [c for c in dict.fromkeys(re.findall(rf"item\.rakuten\.co\.jp/{SHOP_ID}/([\w-]+)/", resp.text)) if c != "c"]
            new = [c for c in page_codes if c not in seen]
            seen.update(page_codes)
            for c in page_codes:
                if c not in codes:
                    codes.append(c)
            time.sleep(REQUEST_INTERVAL)
            if not new:
                break
    return codes


def to_grams(text: str) -> int | None:
    m = UNIT_PATTERN.search(text or "")
    if not m:
        return None
    value = float(m.group(1))
    return int(round(value * 1000)) if m.group(2).lower() in ("kg", "キログラム", "キロ", "k") else int(round(value))


def extract_weight(content: str | None, title: str) -> int | None:
    if content:
        m = re.search(r"合計\s*(\d+(?:\.\d+)?\s*(?:kg|キログラム|キロ|g))", content, re.I)
        w = to_grams(m.group(1)) if m else to_grams(content)
        if w:
            return w
    return to_grams(title)


def clean_title(raw: str) -> str:
    t = unicodedata.normalize("NFKC", raw).replace("【楽天市場】", "")
    t = re.sub(r"[:：]\s*京都西陣珈琲\s*$", "", t)
    return t.strip()


def name_from_title(title: str) -> str | None:
    m = re.search(r"【\s*([^】]+?)\s*】", title)
    if m:
        return m.group(1).strip()
    m = re.search(r"「\s*([^」]+?)\s*」", title)
    return m.group(1).strip() if m else None


def group_key(name: str) -> str:
    key = re.sub(r"[\s　・]+", "", unicodedata.normalize("NFKC", name)).lower()
    return re.sub(r"(hibiki|koto)$", "", key)  # 「響HIBIKI」と「響」、「古都 koto」と「古都」を同一銘柄にする


def coarse_roasts(text: str) -> list[str]:
    found = []
    for label, pat in COARSE_ROASTS:
        # 「中深煎り」中の「深煎り」等の二重検出を避けるため、既に検出した語を除いて判定する
        remaining = text
        for f in found:
            remaining = remaining.replace(f, "")
        if pat.search(remaining) and label not in found:
            found.append(label)
    return found


def parse_item(code: str) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        return None
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    title = clean_title(soup.title.get_text(strip=True)) if soup.title else ""
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    desc_el = soup.select_one("span.sale_desc")
    desc = unicodedata.normalize("NFKC", desc_el.get_text("\n", strip=True)) if desc_el else ""
    nm = re.search(r"商品名[:：]\s*(.+)", desc)
    cm = re.search(r"内容量[:：]\s*(.+)", desc)
    content = cm.group(1).strip() if cm else None
    if content and ("セット" in content or "パックセット" in content):
        return None
    weight = extract_weight(content, title)
    if not weight:
        return None
    name = (nm.group(1).strip() if nm else None) or name_from_title(title)
    if not name:
        return None
    price_m = PRICE_PATTERN.search(html_text)
    avail_m = AVAIL_PATTERN.search(html_text)
    return {
        "code": code, "title": title, "name": name, "weight": weight, "desc": desc,
        "price": int(price_m.group(1)) if price_m else None,
        "sold_out": bool(avail_m) and avail_m.group(1) != "InStock",
    }


def build_record(it: dict) -> dict:
    title, name, desc = it["title"], it["name"], it["desc"]
    is_blend = "ブレンド" in title or "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(name)
        if c:
            parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        if not parsed["origin_country"]:
            om = re.search(r"原産国名?[:：]\s*([^\n]+)", desc)
            c = detect_country_name(om.group(1)) if om else None
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "description"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roasts = coarse_roasts(title)
    selectable = "選べる" in title or len(roasts) > 1
    roast_level, roast_hint = None, None
    if selectable:
        roast_hint = "・".join(roasts) if roasts else "選べる焙煎"
    elif roasts:
        roast_level, roast_hint = roasts[0], roasts[0]
    else:
        rl = parse_product(title)["roast_level"]
        if rl:
            roast_level, roast_hint = rl, rl

    body = desc.split("【1】")[0]
    body = re.sub(r"\s+", " ", body).strip()
    farm = None
    sm = re.search(r"(産地|標高|品種|農園)[:：]\s*([^\n]+)", desc)
    if sm:
        farm = f"{sm.group(1)}: {sm.group(2).strip()}"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else (parsed["processing_method"] or detect_processing_method(title)),
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_selectable": selectable,
        "roast_hint": roast_hint,
        "flavor_notes": body[:300] or None,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": ITEM_URL.format(code=it["code"]),
    }


def scrape_all_products() -> list[dict]:
    items = []
    for code in list_codes():
        try:
            it = parse_item(code)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {code} ({e})")
            continue
        if it:
            items.append(it)
        time.sleep(REQUEST_INTERVAL)
    best = {}
    for it in items:
        k = group_key(it["name"])
        if k not in best or it["weight"] < best[k]["weight"]:
            best[k] = it
    return [build_record(it) for it in best.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_nishijincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishijincoffee.json に出力しました")


if __name__ == "__main__":
    main()
