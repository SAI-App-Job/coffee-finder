# -*- coding: utf-8 -*-
"""
scrape_coffeemameta.py

焙煎工房 豆太(神奈川県川崎市、有限会社ヒューマック運営。オンラインショップ coffee-mameta.com、
カラーミーショップ=coffee-mameta.shop-pro.jp)の自家焙煎コーヒー豆(シングルオリジン)を取得する。

【対象】カテゴリ(ブラジル/コロンビア/グアテマラ/インドネシア/エチオピア/ジャマイカ/その他)と
グループ(500g×1袋・500g×2袋・150g×3袋)の全商品ページを走査し、次を採用する。
 - 商品名の末尾「＜150g×3袋＞」のように、全商品が「袋×本数」の同一銘柄パック。重量は 袋重量×本数(総量)。
   例: マンデリンリントン＜150g×3袋＞ = 450g、¥3,726。
 - 1銘柄につき総量が最小のパックを代表とする(150g×3袋=450g と 500g×2袋=1kg が並ぶ銘柄は450g)。
 - 総量1kg以上のみの銘柄(500g×2袋、500g×3袋)は事業者向け大容量扱いで除外。
 - 「3銘柄コーヒーセット」「3カ国プレミアムコーヒーセット」はセットのため除外。
【価格】商品ページの Colorme JSON の税込価格(通常価格。会員登録時の会員価格は採用しない)。
【在庫】Colorme の stock_num が 0 以下、または一覧に SOLD OUT 表示なら品切れ。
【焙煎度】商品説明の「【焙煎度】中煎り」「「中煎り」焙煎」から取得。
【文字コード】EUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎工房 豆太",
    "url": "https://coffee-mameta.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県川崎市高津区下野毛1-6-14",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ coffee-mameta.com のカテゴリ・グループ一覧と各商品ページを2026-10-21に確認。"
                   "特定商取引法表記(販売業者 有限会社ヒューマック、神奈川県川崎市高津区下野毛1-6-14 焙煎工房 豆太、電話044-322-8095)。"
                   "トップに「焙煎工場が直営するコーヒー豆専門店」「原料仕入れから発送まで一貫した自社内で行う製造販売方式」「本格的焙煎装置で、ご注文後に焙煎」。"
                   "全商品が袋×本数のパック売り(重量は総量)。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://coffee-mameta.com/"
LIST_URLS = [
    BASE_URL + "?mode=grp&gid=1937033",
    BASE_URL + "?mode=grp&gid=1937035",
    BASE_URL + "?mode=grp&gid=2457052",
    BASE_URL + "?mode=grp&gid=2457052&page=2",
] + [BASE_URL + f"?mode=cate&cbid={c}&csid=0" for c in
     (2453432, 2453434, 2453435, 2453436, 2453437, 2453438, 2459986)]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
PACK_RE = re.compile(r"＜\s*(\d+)\s*[gｇ]\s*×\s*(\d+)\s*袋\s*＞")
EXCLUDE = ["セット", "ドリップ", "ギフト"]
ROAST_RE = re.compile(r"【焙煎度】\s*(極深煎り|深煎り|中深煎り|中煎り|中浅煎り|浅煎り|フレンチ|イタリアン|シティ|ハイ)")
ROAST_ALT_RE = re.compile(r"「(極深煎り|深煎り|中深煎り|中煎り|中浅煎り|浅煎り)」焙煎")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(html, "html.parser"), html


def list_items():
    items = {}
    for url in LIST_URLS:
        soup, _ = fetch(url)
        for li in soup.select("li.product-list__unit"):
            a = li.select_one("a.product-list__name")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            name = a.get_text(strip=True)
            if not m or not name or re.match(r"^\d+\s", name):
                continue
            pid = m.group(1)
            sold = "SOLD OUT" in li.get_text(" ", strip=True)
            items.setdefault(pid, {"name": name, "sold": sold})
        time.sleep(DELAY)
    return items


def pick_representatives(items):
    best = {}
    for pid, it in items.items():
        name = unicodedata.normalize("NFKC", it["name"]).replace("＜", "<")
        if any(k in it["name"] for k in EXCLUDE) or "銘柄コーヒー" in it["name"]:
            continue
        m = PACK_RE.search(it["name"])
        if not m:
            continue
        total = int(m.group(1)) * int(m.group(2))
        if total >= 1000:
            continue
        base = unicodedata.normalize("NFKC", it["name"][:m.start()]).replace(" ", "").replace("　", "")
        base_raw = it["name"][:m.start()].strip()
        # 「グァテマラスペシャルティ＜150g×3袋＞アティトゥラン」のように後置の補足があるため、そのまま使う
        if base not in best or total < best[base][2]:
            best[base] = (pid, base_raw, total, it["sold"])
    return list(best.values())


def build(pid, base_name, total, list_sold):
    url = f"{BASE_URL}?pid={pid}"
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    price = p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = list_sold or (isinstance(stock, int) and stock <= 0)

    ex = soup.select_one("div.product__explain")
    for br in (ex.find_all("br") if ex else []):
        br.replace_with("\n")
    body = ex.get_text("\n", strip=True) if ex else ""

    roast = None
    rm = ROAST_RE.search(body) or ROAST_ALT_RE.search(body)
    if rm:
        roast = rm.group(1)

    origin_line = re.search(r"産\s*地\s*名\s*[：:]\s*([^\n]+)", body)
    cup = re.search(r"カップの特長\s*[：:]\s*([^\n]+)", body)
    variety = re.search(r"品\s*種\s*[：:]\s*([^\n]+)", body)
    proc = re.search(r"精\s*選\s*方\s*法\s*[：:]\s*([^\n]+)", body)
    alt = re.search(r"標\s*高\s*[：:]\s*([^\n]+)", body)

    parsed = parse_product(base_name)
    parsed["category"] = "ストレート"
    if not parsed["origin_country"] and origin_line:
        c = detect_country_name(origin_line.group(1))
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "product_description"
    if not parsed["origin_country"]:
        c = detect_country_name(body[:600])
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, base_name)

    # 説明文のうち名称/原材料などの定型行を除いた先頭の説明
    desc_lines = [l for l in body.split("\n") if l.strip()]
    flavor = cup.group(1).strip() if cup else None
    farm_parts = []
    for label, mm in (("産地", origin_line), ("標高", alt), ("品種", variety), ("精選", proc)):
        if mm:
            farm_parts.append(f"{label}: {mm.group(1).strip()}")
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": "、".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": total,
        "stock_status": "品切れ" if out else "販売中",
        "out_of_stock": bool(out),
        "product_url": url,
    }


def main():
    items = list_items()
    reps = pick_representatives(items)
    print(f"[info] 一覧 {len(items)}件 / 代表 {len(reps)}銘柄")
    records = []
    for pid, base_name, total, sold in reps:
        time.sleep(DELAY)
        try:
            rec = build(pid, base_name, total, sold)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_coffeemameta.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeemameta.json に出力しました")


if __name__ == "__main__":
    main()
