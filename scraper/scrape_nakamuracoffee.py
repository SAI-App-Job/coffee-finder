# -*- coding: utf-8 -*-
"""
scrape_nakamuracoffee.py

NAKAMURA coffee(KOBE ナカムラコーヒー / 神戸クラフトコーヒー焙煎所、1936年創業、
nakamuracoffee.shop-pro.jp、兵庫県神戸市兵庫区中道通3-2-11、中村珈琲株式会社)の商品情報を
取得する。カラーミーショップ(EUC-JP)。

【店舗数の確認(2026-10)】
特定商取引法ページの販売業者は中村珈琲株式会社(兵庫区中道通3-2-11)のみで、他店舗の記載は無く
単独店舗と判断した。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(?mode=srh)の55件から、焙煎豆のブレンド・
ストレート・スペシャルティ・デカフェを対象とする。リキッド/水出しアイスコーヒー、カフェオレベース、
ドリップコーヒー、「選べる○○」「ギフト」「セット」「飲み比べ」、紅茶・ジュースは除外。
詳細ページに「インフューズド」(焙煎前に香料エキスを付ける製法)と明記された商品は
フレーバー扱いとして別枠(flavored_products_excluded)に分離する。
ブレンドは「<名>270g(90g×3)」「<名>900g(180g×5)」のように複数袋のパッケージ売りのみで、
同名ブレンドは最小の総重量(270g/300g)の商品を代表とし、weight_gは総重量(袋数×1袋の重量)。
価格はColormeのJSON(税込)、在庫は一覧の「SOLD OUT」表示で判定する。
"""

import json
import re
import time
import unicodedata
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method, ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "NAKAMURA coffee",
    "url": "https://nakamuracoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro)",
    "address": "兵庫県神戸市兵庫区中道通3-2-11",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://nakamuracoffee.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["選べる", "ギフト", "セット", "飲み比べ", "ドリップコーヒー", "リキッド", "水出し",
                    "カフェオレベース", "ティー", "ジュース", "送料"]
WEIGHT_STRIP = re.compile(r"\s*\(?\s*\d+\s*(?:kg|g)\b.*$", re.IGNORECASE)
PACK_PATTERN = re.compile(r"(\d+)\s*g\s*[x×]\s*(\d+)", re.IGNORECASE)
INFUSED_CATEGORY_ID = "2972888"  # 「インヒューズドコーヒー」カテゴリ(香料・果実等を加える製法のためフレーバー扱い)
ORIGIN_OVERRIDES = {"ンゴロンゴロ": "タンザニア"}
WEIGHT_NAME = re.compile(r"(\d+)\s*(kg|g)", re.IGNORECASE)
COLORME_JSON = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
LABEL_RE = re.compile(r"^(原産国|地域|農園|標高|精選|精製|品種|規格|煎り具合|焙煎度)[\s:：]+(.+)$")


def fetch(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def name_weight(title: str) -> int | None:
    pk = PACK_PATTERN.search(title)
    if pk and not re.search(r"\d+\s*(?:kg|g)\s*\(\s*\d+\s*g", title, re.IGNORECASE):
        return int(pk.group(1)) * int(pk.group(2))
    m = WEIGHT_NAME.search(title)
    if not m:
        return None
    return int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)


def infused_pids() -> set[str]:
    soup, _ = fetch(f"{BASE_URL}?mode=cate&cbid={INFUSED_CATEGORY_ID}&csid=0")
    return {m.group(1) for a in soup.select("li.productlist-unit a")
            if (m := re.search(r"pid=(\d+)", a.get("href", "")))}


def list_items() -> list[dict]:
    items, page = [], 1
    while True:
        soup, _ = fetch(f"{BASE_URL}?mode=srh&keyword=&sort=n&page={page}")
        units = soup.select("li.productlist-unit")
        if not units:
            break
        for u in units:
            a = u.select("a")[-1]
            title = norm(a.get_text(" ", strip=True))
            if any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            items.append({
                "title": title,
                "pid": re.search(r"pid=(\d+)", a["href"]).group(1),
                "sold_out": "SOLD OUT" in u.get_text(),
            })
        page += 1
        time.sleep(0.5)
    return items


def build_record(it: dict):
    url = f"{BASE_URL}?pid={it['pid']}"
    soup, raw = fetch(url)
    price, variant_weight = None, None
    m = COLORME_JSON.search(raw)
    if m:
        prod = json.loads(m.group(1)).get("product", {})
        price = prod.get("sales_price_including_tax")
        # 50g/100gのようにサイズ違いのバリエーションがある商品は最小サイズの価格を代表とする
        sized = []
        for v in prod.get("variants", []):
            wm = re.search(r"(\d+)\s*g", norm(v.get("option1_value") or ""))
            if wm:
                sized.append((int(wm.group(1)), v.get("option_price_including_tax")))
        if sized:
            variant_weight, price = min(sized)
    for x in soup(["script", "style"]):
        x.decompose()
    exp = soup.select_one(".product-order-exp")
    lines = [norm(ln) for ln in exp.get_text("\n", strip=True).split("\n")] if exp else []
    lines = [ln for ln in lines if ln]
    # 本文は「【豆の挽き方】」「【コーヒー袋】」「※」より前
    body = []
    for ln in lines:
        if ln.startswith("【豆の挽き方】") or ln.startswith("【コーヒー袋】") or ln.startswith("※"):
            break
        body.append(ln)
    labels, desc = {}, []
    for ln in body:
        mm = LABEL_RE.match(ln)
        if mm:
            labels[mm.group(1)] = mm.group(2).strip()
        elif not re.match(r"^(香り|コク|苦味|甘味|酸味)", ln) and not ln.startswith("【テイスト】"):
            desc.append(ln)

    title = it["title"]
    name = WEIGHT_STRIP.sub("", title).strip()
    weight = variant_weight or name_weight(title)
    processing_raw = labels.get("精選") or labels.get("精製") or ""
    if it["pid"] in INFUSED_PIDS or "インフューズド" in processing_raw:
        return None, {"shop_name": SHOP_INFO["name"], "raw_name": name, "category": "フレーバー",
                      "is_flavored": True, "price": price, "product_url": url}

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        for kw, country in ORIGIN_OVERRIDES.items():
            if not parsed["origin_country"] and kw in name:
                parsed["origin_country"], parsed["origin_source"] = country, "region_name"
        if not parsed["origin_country"] and labels.get("原産国"):
            c = detect_country_name(labels["原産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and processing_raw:
            processing = normalize_processing_method(processing_raw)
    roast_text = labels.get("煎り具合") or labels.get("焙煎度") or ""
    roast_text = re.sub(r"^煎り具合[\s:：]*", "", roast_text)
    # 「シティー&イタリアン」「ハイロースト(もしくはシティロースト)」のように複数の焙煎度が
    # 併記されている場合は1つに決められないためroast_levelはNone(roast_hintに原文を残す)
    matched = []
    for kw, rl in ROAST_KEYWORDS.items():
        if kw in roast_text and rl not in matched:
            matched.append(rl)
    roast_level = matched[0] if len(matched) == 1 else None
    farm_bits = [f"{k}: {labels[k]}" for k in ("地域", "農園", "標高", "品種", "規格") if labels.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_text or None,
        "flavor_notes": (" ".join(desc[-6:]))[:300] if desc else None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": url,
    }, None


INFUSED_PIDS: set[str] = set()


def scrape_all_products():
    INFUSED_PIDS.update(infused_pids())
    groups = OrderedDict()
    for it in list_items():
        name = WEIGHT_STRIP.sub("", it["title"]).strip()
        w = name_weight(it["title"]) or 10**9
        cur = groups.get(name)
        if cur is None or w < cur[0]:
            groups[name] = (w, it)
    records, flavored = [], []
    for w, it in groups.values():
        try:
            rec, flv = build_record(it)
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['pid']} ({e})")
            continue
        if rec:
            records.append(rec)
        if flv:
            flavored.append(flv)
        time.sleep(0.5)
    return records, flavored


def main():
    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records, "flavored_products_excluded": flavored}
    with open("data_nakamuracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nakamuracoffee.json に出力しました(フレーバー除外{len(flavored)}件)")


if __name__ == "__main__":
    main()
