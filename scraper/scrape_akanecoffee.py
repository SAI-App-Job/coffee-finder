# -*- coding: utf-8 -*-
"""
scrape_akanecoffee.py

茜珈琲(アカネコーヒー、東京都町田市鶴川2-2-11、公式 https://akane-coffee.shop-pro.jp/)の
自家焙煎コーヒー豆の商品情報を取得する。カラーミーショップ(shop-pro.jp)、EUC-JP。

【実店舗・自家焙煎の根拠】(2026-10-25確認)
トップ・店舗案内に「茜珈琲は東京都町田市鶴川にある自家焙煎珈琲豆の販売店です」「本格自家焙煎コーヒー豆専門店」、
特商法表記(?mode=sk)で所在地「東京都町田市鶴川2-2-11」、?mode=f2「場所・ご来店方法」で小田急鶴川駅徒歩13分・駐車場・水曜定休。

【robots.txt】/secure/ と /cart/ のみ Disallow(2026-10-25確認)。カテゴリ一覧・商品詳細のみ取得する。

【対象商品】
カテゴリ「茜珈琲のコーヒー豆(焙煎)」(cbid=1236311、全ページ)の商品のうち、セット・飲み比べ・お試しセットを除く
100g単位のストレート・ブレンド・カフェインレス。生豆カテゴリ・コーヒーミルは対象外。
価格はカートの既定(そのまま=シティロースト・豆の状態)の税込価格。深煎りへの変更(ダブルロースト)は
+50円/100gのオプションで、代表価格には含めない。

【産地】商品名の末尾［地域/国］の国名(ブレンドは複数国)、詳細ページの「原産国・農園名」を農園メモに入れる。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "茜珈琲",
    "url": "https://akane-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都町田市鶴川2-2-11",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ(https://akane-coffee.shop-pro.jp/)の「茜珈琲のコーヒー豆(焙煎)」カテゴリと各商品ページを2026-10-25に確認。特商法表記(?mode=sk)・店舗案内(?mode=f2)で所在地・実店舗を確認。トップの店長挨拶は「10月です」(当月分に更新)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://akane-coffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=1236311&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 2
NON_BEAN_KEYWORDS = ["セット", "飲み比べ", "ドリップバッグ", "ギフト", "ミル"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"［\s*(\d+)\s*[gｇ]\s*］")
BRACKETS = re.compile(r"［[^］]*］")


def fetch(url: str) -> tuple[BeautifulSoup, str]:
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(text, "html.parser"), text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup, _ = fetch(url)
        found = 0
        for d in soup.select("div.product_list"):
            a = d.select_one("div.name a")
            if not a or not a["href"].startswith("?pid="):
                continue
            found += 1
            name = clean(a.get_text())
            if any(k in name for k in NON_BEAN_KEYWORDS) or a["href"] in seen:
                continue
            seen.add(a["href"])
            items.append({
                "url": BASE_URL + a["href"],
                "list_name": name,
                "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫なし", d.get_text(" "))),
            })
        time.sleep(CRAWL_DELAY_SECONDS)
        if not found:
            break
    return items


def after_label(lines: list[str], label: str) -> str | None:
    for i, l in enumerate(lines):
        if l == label and i + 1 < len(lines):
            return lines[i + 1]
    return None


def detect_decaf(desc: str | None) -> str:
    d = desc or ""
    if "スイス" in d:
        return "スイスウォータープロセス(水抽出法、薬品不使用)"
    if "マウンテン・ウォーター" in d or "マウンテンウォーター" in d:
        return "マウンテンウォータープロセス(水抽出法、薬品不使用)"
    if "液体二酸化炭素" in d:
        return "液体CO2抽出によりカフェインを除去"
    return "カフェインレス(除去方法の詳細記載なし)"


def build_record(item: dict) -> dict | None:
    soup, text = fetch(item["url"])
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        print(f"[warn] Colorme JSON なし: {item['url']}")
        return None
    product = json.loads(m.group(1)).get("product") or {}
    full_name = clean(product.get("name") or item["list_name"])
    # 豆のまま(挽かない)・既定の焙煎(そのまま)の最小価格
    price = product.get("sales_price_including_tax")
    for v in product.get("variants") or []:
        if "そのまま" in (v.get("option1_value") or "") and "豆の状態" in (v.get("option2_value") or ""):
            price = v.get("option_price_including_tax")
            break
    wm = WEIGHT_PATTERN.search(full_name)
    weight = int(wm.group(1)) if wm else None
    brackets = BRACKETS.findall(full_name)
    country_part = brackets[-1].strip("［］") if brackets else ""
    name = clean(BRACKETS.sub("", full_name).replace("（焙煎）", "").replace("(焙煎)", ""))

    body = soup.get_text("\n", strip=True).split("\n")
    lines = [clean(l) for l in body if clean(l)]
    roast_raw = after_label(lines, "焙煎具合")
    origin_line = after_label(lines, "原産国・農園名")
    bean_type = after_label(lines, "豆の種類")
    # 商品説明: 「［100ｇ］」直後の最初の説明行
    desc = None
    desc_full = None
    start = next((i for i, l in enumerate(lines) if l.startswith("» 特定商取引法に基づく表記")), None)
    if start is not None:
        for i in range(start + 1, min(start + 6, len(lines))):
            if lines[i].endswith("］") and WEIGHT_PATTERN.search(lines[i]):
                desc_lines = []
                for l in lines[i + 1:i + 8]:
                    if l.startswith("商品名"):
                        break
                    desc_lines.append(l)
                desc = " ".join(desc_lines) or None
                desc_full = desc
                desc = desc[:400] if desc else None
                break
    stock = product.get("stock_num")
    sold_out = item["sold_out"] or (isinstance(stock, int) and stock <= 0)

    is_decaf = "カフェインレス" in full_name
    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        blend_components = [c.strip() for c in country_part.split("/") if c.strip()]
    else:
        blend_components = []
        country = detect_country_name(country_part.split("/")[-1]) or detect_country_name(name)
        parsed["category"] = "ストレート"
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_page"
        parsed = apply_category_hint_fallback(parsed, name)
    farm_parts = []
    if origin_line and not is_blend:
        farm_parts.append(f"原産国・農園名: {origin_line}")
    if bean_type:
        farm_parts.append(f"豆の種類: {bean_type}")
    roast = None
    if roast_raw:
        rm = re.search(r"(ライト|シナモン|ミディアム|ハイ|シティ|フルシティ|フレンチ|イタリアン)ロースト", roast_raw)
        roast = rm.group(0) if rm else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": " / ".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "decaf_process": detect_decaf(desc_full) if is_decaf else None,
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if sold_out else "販売中",
        "out_of_stock": bool(sold_out),
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in scrape_list():
        try:
            rec = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_akanecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_akanecoffee.json に出力しました")


if __name__ == "__main__":
    main()
