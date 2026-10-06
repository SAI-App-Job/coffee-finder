# -*- coding: utf-8 -*-
"""
scrape_itokucoffee.py

ITOKU COFFEE(www.store-itokucoffee.com、ショップサーブ、UTF-8)の商品情報を取得する。
静岡県伊東市玖須美元和田716-396(特定商取引法表示 /hpgen/HPB/shop/business.html で確認)。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「ストレート」(/SHOP/27416/list.html、35件)と
「ブレンド」(/SHOP/26935/list.html、7件)カテゴリの計42商品を対象とする(いずれも焙煎豆。
デカフェ「メキシコ ハニーチアパス カフェインレス」はストレートに含まれる)。
「コーヒーセット(お試し4種セット)」「ドリップバッグ」「コールドブリューコーヒーバッグ」
「コーヒーギフト」はカテゴリが別のため対象外。

【価格・重量・在庫】
各商品ページに「挽き方 × グラム数(100g/200g/500g)」のバリエーション表があり、
「豆のまま」の最小重量(100g)の税込価格を代表として採用する。1商品のみ(COE入賞ロット)は
バリエーション表が無く、100gのみの商品のため、商品価格欄の税込価格を使う。
在庫は商品ページの「在庫:」欄(#stock)が「×」の場合に完売とする。

【焙煎度について】
「浅煎り/中煎り/中深煎り/深煎り」の4カテゴリのいずれか1つだけに属する商品はそのカテゴリを
roast_levelとする。複数カテゴリに属する商品(ジャーマンミックス、ルワンダ カビリジ等)は
roast_levelをNoneとし、商品ページの「中煎り〜中深煎り / シティロースト」のような表記が
あればroast_hintとして保持する。

【robots.txtについて】
/robots.txt は404(制限の記述なし、2026-10確認)。識別可能な独自User-Agentを使用し、
アクセス間隔を空ける。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "ITOKU COFFEE",
    "url": "https://www.store-itokucoffee.com/",
    "platform": "ショップサーブ",
    "address": "静岡県伊東市玖須美元和田716-396",
    "prefecture": "静岡県",
    "robots_txt_status": "制限なし(/robots.txtは404。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.store-itokucoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
MAX_PAGES = 5

STRAIGHT_LIST = "/SHOP/27416/list.html"
BLEND_LIST = "/SHOP/26935/list.html"
ROAST_LISTS = {
    "浅煎り": "/SHOP/183485/list.html",
    "中煎り": "/SHOP/183486/list.html",
    "中深煎り": "/SHOP/183487/list.html",
    "深煎り": "/SHOP/183488/list.html",
}

# 商品名の先頭語から国名を補う(辞書は「タイ」を誤爆防止のため含まない)
ORIGIN_OVERRIDES = {"タイ": "タイ"}

NO_PROCESS_PATHS = {"/SHOP/10182.html"}  # メキシコ ハニーチアパス カフェインレス(商品名の一部であり精製方法ではない)

PRICE_PATTERN = re.compile(r"税込\s*[¥￥]\s*([\d,]+)")
ROAST_HINT_PATTERN = re.compile(r"^(?:浅|中浅|中|中深|深)煎り.*ロースト.*$")


def fetch(url: str) -> str:
    last = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def list_paths(list_path: str) -> list[tuple[str, str]]:
    """カテゴリ一覧から (商品パス, 商品名) を全ページ分集める。"""
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        path = list_path if page == 1 else list_path.replace("list.html", f"list{page}.html")
        try:
            soup = BeautifulSoup(fetch(BASE_URL + path), "html.parser")
        except requests.RequestException:
            break
        new = 0
        for a in soup.select('h2 a[href*="/SHOP/"]'):
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            items.append((href, re.sub(r"\s+", " ", a.get_text(strip=True)).strip()))
        if new == 0:
            break
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")

    # 在庫(#stock): ○=あり、×=完売
    stock_el = soup.select_one("#stock")
    stock_sym = re.sub(r"\s+", "", stock_el.get_text()) if stock_el else None

    # バリエーション表から「豆のまま」の最小重量の税込価格を取る
    price, weight = None, None
    var = soup.select_one("table.variation")
    if var:
        cur = None
        best = None
        for tr in var.select("tr")[1:]:
            tds = tr.select("td")
            if len(tds) >= 3:
                cur = tds[0].get_text(strip=True)
                g, pr = tds[1].get_text(strip=True), tds[2].get_text(" ", strip=True)
            elif len(tds) == 2:
                g, pr = tds[0].get_text(strip=True), tds[1].get_text(" ", strip=True)
            else:
                continue
            gm = re.match(r"(\d+)\s*g", g)
            pm = PRICE_PATTERN.search(pr)
            if cur == "豆のまま" and gm and pm:
                w = int(gm.group(1))
                if best is None or w < best[0]:
                    best = (w, int(pm.group(1).replace(",", "")))
        if best:
            weight, price = best

    for sc in soup(["script", "style"]):
        sc.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n")]

    if price is None:
        # バリエーション表が無い商品(100gのみ): 商品価格欄の税込価格と、在庫表の「豆のまま 100g」から取る
        m = PRICE_PATTERN.search("\n".join(lines))
        if m:
            price = int(m.group(1).replace(",", ""))
        for i, l in enumerate(lines):
            if l == "豆のまま" and i + 2 < len(lines) and re.match(r"^\d+g$", lines[i + 1]):
                weight = int(lines[i + 1][:-1])
                if stock_sym is None:
                    stock_sym = lines[i + 2]
                break

    # 説明文: 「返品についてはコチラをご確認ください」から「会員メニュー」の手前まで
    desc, roast_hint = None, None
    try:
        start = max(i for i, l in enumerate(lines) if l.startswith("返品についてはコチラ"))
    except ValueError:
        start = None
    if start is not None:
        end = next((i for i in range(start + 1, len(lines)) if lines[i] == "会員メニュー"), len(lines))
        body = lines[start + 1:end]
        for l in body:
            if ROAST_HINT_PATTERN.match(l):
                roast_hint = l
                break
        # 【INFORMATION】以降(品名・原材料名等の定型)は除外し、【コメント】の見出しは除く
        text_lines = []
        for l in body:
            if l.startswith("【INFORMATION】") or l.startswith("■INFORMATION"):
                break
            if l in ("【コメント】", "■コメント"):
                continue
            text_lines.append(l)
        desc = re.sub(r"\s+", " ", " ".join(text_lines)).strip()[:400] or None

    return {"price": price, "weight": weight, "stock_sym": stock_sym, "desc": desc, "roast_hint": roast_hint}


def build_record(path: str, title: str, is_blend: bool, roast_categories: set[str]) -> dict | None:
    detail = parse_detail(fetch(BASE_URL + path))
    name = re.sub(r"\s+", " ", title.replace("　", " ")).strip()

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            override = next((c for k, c in ORIGIN_OVERRIDES.items() if name.startswith(k)), None)
            detected = override or detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    # ブレンドは「モカ ＆ スマトラ」のように産地名を含むだけで精製方法ではないため、精製方法は付けない。
    # 「メキシコ ”ハニーチアパス” カフェインレス」の「ハニー」は商品名の一部で精製方法の表記ではない。
    if is_blend or path in NO_PROCESS_PATHS:
        parsed["processing_method"] = None
    elif parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(parsed["processing_method"])

    roast_level = next(iter(roast_categories)) if len(roast_categories) == 1 else None
    sold_out = detail["stock_sym"] in ("×", "✕", "x", "X")

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": detail["roast_hint"],
        "flavor_notes": detail["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": detail["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": BASE_URL + path,
    }


def scrape_all_products() -> list[dict]:
    roast_map: dict[str, set[str]] = {}
    for roast, lp in ROAST_LISTS.items():
        for href, _ in list_paths(lp):
            roast_map.setdefault(href, set()).add(roast)

    targets = [(h, t, False) for h, t in list_paths(STRAIGHT_LIST)]
    seen = {h for h, _, _ in targets}
    targets += [(h, t, True) for h, t in list_paths(BLEND_LIST) if h not in seen]

    records = []
    for href, title, is_blend in targets:
        try:
            record = build_record(href, title, is_blend, roast_map.get(href, set()))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {href} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_itokucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_itokucoffee.json に出力しました")


if __name__ == "__main__":
    main()
