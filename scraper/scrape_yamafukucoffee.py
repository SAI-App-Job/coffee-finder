# -*- coding: utf-8 -*-
"""
scrape_yamafukucoffee.py

ヤマフクコーヒー(北海道枝幸郡中頓別町字中頓別141、運営 guffaw ヤマフクコーヒー事業部)の
公式ショップ shop.yamafukucoffee.com の商品情報を取得する。

【販売先について】
公式サイト(www.yamafukucoffee.com)の「コーヒー豆を通販で購入」の導線先が shop.yamafukucoffee.com。
このショップの先頭に「確認用サイトです。お支払いの可否は購入画面でご確認ください。」の文言があるが、
HTMLでは `<div class="demo" data-store-preview hidden>` で非表示(プレビュー時のみ表示する部品)であり、
`<meta name="yamafuku-store-mode" content="production">`・`yamafuku-public-indexing=enabled`、
特商法表記(guffaw ヤマフクコーヒー事業部)・旧店舗レビューの移行もあるため本番ECと判断した。
楽天市場店(www.rakuten.co.jp/yamafukucoffee/)は「店舗の改装中」の閉鎖ページで商品なし。Yahoo!ショッピングも出店なし。

【取得方法】
/api/ は robots.txt で禁止のため使わない。トップページ(`/`)のSSR済み商品カードと、各商品ページ
(`/view/item/<id>`、SSR済み)のみを使う。商品ページには在庫表示が無い(在庫はJS+/api)ため、
在庫は「販売中」として扱う。

【対象商品について】
12銘柄(オリジナルブレンド・オリジナルエスプレッソブレンド・シングルオリジン10種)を、
各銘柄の最小重量=150gで登録する(200g・300gは同一銘柄の大きいサイズのため対象外)。
除外: サンプル(50g)、ドリップバッグ、生豆。
"""

import html
import json
import re
import time
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "ヤマフクコーヒー",
    "url": "https://shop.yamafukucoffee.com/",
    "platform": "独自EC(自社構築)",
    "address": "北海道枝幸郡中頓別町字中頓別141",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10確認。Allow: /、Disallow は /admin /api/ /business/ /checkout /orders /view/member/ /view/cart /search 等。トップページと /view/item/ のみ使用)",
    "source_note": "公式ショップ(https://shop.yamafukucoffee.com/)のトップと各商品ページを2026-10-20に確認。公式サイト(https://www.yamafukucoffee.com/)に"
                   "「自家焙煎コーヒー」「受注後に焙煎」、住所・営業時間11:00-18:30の記載(カフェ併設)。各銘柄の最小容量150gを採用。在庫表示は商品ページに無いため販売中扱い",
    "last_verified_at": "2026-10-20",
}

BASE = "https://shop.yamafukucoffee.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 2
EXCLUDE = ("サンプル", "ドリップバッグ", "生豆", "セット")
CARD = re.compile(r'<article class="card"><a href="(/view/item/\d+)">.*?<h3>(.*?)</h3><div class="price">(.*?)</div>', re.S)
ROAST = re.compile(r"(中浅煎り|中深煎り|浅煎り|深煎り|中煎り)")


def get(url: str) -> str:
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    return resp.content.decode("utf-8")


def list_cards() -> list[dict]:
    text = get(BASE + "/")
    cards = []
    for href, name, price in CARD.findall(text):
        name = html.unescape(name).strip()
        wm = re.search(r"(\d+)g$", unicodedata.normalize("NFKC", name))
        pm = re.search(r"([\d,]+)円", price)
        if not wm or not pm or any(k in name for k in EXCLUDE):
            continue
        cards.append({"href": href, "name": name, "weight": int(wm.group(1)), "price": int(pm.group(1).replace(",", ""))})
    return cards


def pick_min_weight(cards: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for c in cards:
        base = re.sub(r"\s*\d+g$", "", c["name"]).strip()
        c["base"] = base
        if base not in best or c["weight"] < best[base]["weight"]:
            best[base] = c
    return list(best.values())


def item_info(href: str) -> dict:
    text = get(BASE + href)
    soup = BeautifulSoup(text, "html.parser")
    ps = [p.get_text("\n", strip=True) for p in soup.select(".detail-grid section p")]
    notes = None
    if ps:
        lines = [ln.strip() for ln in ps[0].splitlines() if ln.strip()]
        # 「味わいの目安(星)」「焙煎度」「こんな方におすすめ(✓)」のブロックと、受注後焙煎以降の定型文を除いた紹介文
        kept = []
        for ln in lines:
            if ln.startswith("当店のコーヒー豆は受注後に焙煎"):
                break
            if ln.startswith("✓") or re.match(r"^(味わいの目安|焙煎度|こんな方におすすめ)$", ln) or re.match(r"^(苦味|酸味|コク|甘み)\s*[★☆]+$", ln) or ROAST.fullmatch(ln):
                continue
            kept.append(ln)
        notes = re.sub(r"\s+", " ", " ".join(kept)).strip()[:300] or None
    return {"notes": notes}


def build_record(c: dict, info: dict) -> dict:
    base = c["base"]
    rm = ROAST.search(base)
    roast = rm.group(1) if rm else None
    name = ROAST.sub("", base).strip()
    name = re.sub(r"\s+", " ", name)
    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
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
        "flavor_notes": info["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": c["price"],
        "weight_g": c["weight"],
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": BASE + c["href"],
    }


def scrape_all_products() -> list:
    picks = pick_min_weight(list_cards())
    records = []
    for c in picks:
        time.sleep(INTERVAL)
        records.append(build_record(c, item_info(c["href"])))
    return records


def main():
    records = scrape_all_products()
    with open("data_yamafukucoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamafukucoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], "|", (r["flavor_notes"] or "")[:60])


if __name__ == "__main__":
    main()
