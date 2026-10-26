# -*- coding: utf-8 -*-
"""
scrape_baisenkouboushimano.py

焙煎香房シマノ(大阪府大阪狭山市茱萸木4丁目238-1。1958年創業のスペシャルティコーヒー専門の焙煎所&カフェ。
baisenkoubou-shimano-shop.com、カラーミーショップ独自ドメイン、charset=EUC-JP)の商品情報を取得する。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、約8ページ)の商品のうち、焙煎豆のみ。
同じ銘柄が【200g】と【500g】の別商品ページで並ぶため、銘柄名(【〜g】を除いた商品名)でまとめ、
最小重量(通常200g)の商品を代表にする。次は対象外: 今月のおススメ(通常商品と同じ豆の40円引きクーポン的
別ページ)、グァテマラ カスカラ(コーヒーチェリーの果皮でありコーヒー豆ではない)、ドリップバッグ、セット。
【価格】商品ページの税込価格(内税)。選択肢は「焙煎度×豆/粉」でどれも同額。売切れ商品の一部は価格が
0円表示のため price は null とする。
【焙煎度】注文時に7段階(極浅煎り〜極深煎り)から選択式。roast_level は null、roast_selectable=True とし、
商品ごとの「オススメ焙煎」を roast_hint に記す。
【在庫】カートボタンが「SOLD OUT」(button.c-btn-cart.is-soldout)なら品切れ。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
    detect_stock_status,
)

SHOP_INFO = {
    "name": "焙煎香房シマノ",
    "url": "https://baisenkoubou-shimano-shop.com/",
    "platform": "カラーミーショップ(独自ドメイン baisenkoubou-shimano-shop.com)",
    "address": "大阪府大阪狭山市茱萸木4丁目238-1",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "https://baisenkoubou-shimano-shop.com/ の商品一覧・各商品ページ・特商法(?mode=sk)、公式 "
                   "https://www.baisenkoubou-shimano.com/ を2026-10-26に確認。公式のお知らせは2026-10-09更新(新物入荷)。"
                   "同一銘柄は200g/500gの別ページのため最小重量の200gを代表にした。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://baisenkoubou-shimano-shop.com/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 2.0
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("今月のおススメ", "カスカラ", "ドリップ", "セット", "ギフト", "福袋", "定期便")
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
WEIGHT_RE = re.compile(r"【\s*(\d+)\s*g\s*】")
REGION_ALIAS = {"マンデリン": "インドネシア", "スマトラ": "インドネシア", "トラジャ": "インドネシア"}
DATA_LABELS = ("農園名", "農園主", "生産者", "エリア", "品種", "プロセス", "標高", "オススメ焙煎")


def fetch(url: str) -> str:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> dict[str, str]:
    items: dict[str, str] = {}
    for page in range(1, 15):
        soup = BeautifulSoup(fetch(LIST_URL + ("" if page == 1 else f"&page={page}")), "html.parser")
        new = 0
        for a in soup.find_all("a", href=re.compile(r"^\?pid=\d+")):
            pid = re.search(r"pid=(\d+)", a["href"]).group(1)
            name = re.sub(r"[\s　]+", " ", a.get_text(" ", strip=True))
            if pid not in items:
                items[pid] = name
                new += 1
            elif name and not items[pid]:
                items[pid] = name
        if new == 0:
            break
    return items


def group_key(name: str) -> str:
    return re.sub(r"\s*【\s*\d+\s*g\s*】", "", unicodedata.normalize("NFKC", name)).strip()


def weight_of(name: str) -> int | None:
    m = WEIGHT_RE.search(unicodedata.normalize("NFKC", name))
    return int(m.group(1)) if m else None


def choose_representatives(items: dict[str, str]) -> list[str]:
    groups: dict[str, list[tuple[int, str]]] = {}
    for pid, name in items.items():
        if not name or any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        w = weight_of(name)
        groups.setdefault(group_key(name), []).append((w if w is not None else 10**6, pid))
    return [min(v)[1] for v in groups.values()]


def origin_from(text: str) -> str | None:
    c = detect_country_name(text)
    if c:
        return c
    for kw, country in REGION_ALIAS.items():
        if kw in text:
            return country
    return parse_product(text).get("origin_country")


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    product = (json.JSONDecoder().raw_decode(html, m.end())[0]).get("product") or {}
    title = re.sub(r"[\s　]+", " ", product.get("name") or "").strip()
    if not title:
        return None
    soup = BeautifulSoup(html, "html.parser")
    sold_out = soup.select_one("button.c-btn-cart.is-soldout") is not None
    explain = soup.select_one("div.p-product-explain__body")
    first_para = None
    if explain:
        p = explain.find("p")
        if p:
            first_para = unicodedata.normalize("NFKC", p.get_text(" ", strip=True)) or None

    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [unicodedata.normalize("NFKC", l.strip()) for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]
    data = {}
    if "コーヒー豆 データ" in lines:
        start = lines.index("コーヒー豆 データ")
        i = start + 1
        while i < len(lines) - 1 and lines[i] in DATA_LABELS:
            data[lines[i]] = lines[i + 1]
            if lines[i] == "オススメ焙煎":
                break
            i += 2

    price = product.get("sales_price_including_tax") or None
    weight = weight_of(title)

    parsed = parse_product(title)
    if "ブレンド" in title and "ブレンド" not in data.get("プロセス", ""):
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        country = origin_from(title)
        parsed["origin_country"] = country
        parsed["origin_source"] = "country_name" if country else None
        parsed = apply_category_hint_fallback(parsed, title)

    raw_process = re.sub(r"^チュラル", "ナチュラル", data.get("プロセス", ""))  # 店側の誤記(ナ抜け)を補正
    processing = normalize_processing_method(raw_process) if raw_process else parsed["processing_method"]
    farm_parts = []
    for key in ("農園名", "農園主", "生産者", "エリア", "標高", "品種"):
        if data.get(key):
            farm_parts.append(f"{key}: {data[key]}")
    farm_note = "、".join(farm_parts) or None

    roast_hint = "焙煎度を7段階(極浅煎り〜極深煎り)から選択"
    if data.get("オススメ焙煎"):
        roast_hint += f"(オススメ焙煎: {data['オススメ焙煎']})"

    stock_status = detect_stock_status(title, structural_out_of_stock=sold_out)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_selectable": True,
        "roast_hint": roast_hint,
        "flavor_notes": first_para,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    items = list_items()
    records = []
    for pid in choose_representatives(items):
        rec = build_record(pid)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_baisenkouboushimano.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisenkouboushimano.json に出力しました")


if __name__ == "__main__":
    main()
