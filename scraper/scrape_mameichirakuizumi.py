# -*- coding: utf-8 -*-
"""
scrape_mameichirakuizumi.py

豆一珈楽(まめいちからく。大阪府和泉市唐国町1-9-57。自家焙煎珈琲豆専門店。mame1coffee.com、
カラーミーショップ独自ドメイン、charset=EUC-JP)の商品情報を取得する。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、複数ページ。サイドバーのランキング商品も同じ商品なので
pidで重複排除)の全商品ページ(約64件。すべて焙煎豆。器具・セット・ギフトは取り扱いなし)。
商品名の「有機生豆100%」は原料(JAS認証の有機生豆)の意味で、生豆の販売ではない(焙煎豆)。
【価格・重量】販売価格(税込)。選択肢は「焙煎度×挽き方」でどれも同額。豆のまま(挽き方)の価格を採用。
重量は説明文「1袋 200g」「合計 200g」等(「160g購入で40g無料進呈=合計200g」の商品あり)から取得。
【焙煎度】注文時に8段階(ライト〜イタリアン)から選択式(「お店におまかせ」の既定値は商品ごとに異なる)。
roast_level は null、roast_selectable=True とし、選択肢と既定値を roast_hint に記す。
【在庫】「カートに入れる」ボタンが無い商品は品切れ(サイドバーのSOLD OUT表示は別商品なので使わない)。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
    normalize_processing_method, detect_stock_status,
)

SHOP_INFO = {
    "name": "豆一珈楽",
    "url": "https://mame1coffee.com/",
    "platform": "カラーミーショップ(独自ドメイン mame1coffee.com)",
    "address": "大阪府和泉市唐国町1-9-57",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "https://mame1coffee.com/ の商品一覧・各商品ページ・特商法(?mode=sk)を2026-10-26に確認。"
                   "トップ文言「煎りたて専門の大阪和泉市の自家焙煎珈琲豆専門店」。焙煎度は8段階(ライト〜イタリアン)から選択式のため"
                   "roast_levelはnull。サイト下部の著作権表記は2010年起点で商品は2024年登録分も掲載。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://mame1coffee.com/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 2.0
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
EXCLUDE_KEYWORDS = ("ドリップバッグ", "ギフト", "セット", "福袋", "定期便")
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
REGION_ALIAS = {
    "バリ": "インドネシア", "マンデリン": "インドネシア", "トラジャ": "インドネシア", "スマトラ": "インドネシア",
    "キューバ": "キューバ", "ケニヤ": "ケニア",
}
LABEL_RE = re.compile(r"^(国|エリア|生産者|標高|品種|生産処理|精選方法)\s*[:：]\s*(.+)$")


def fetch(url: str) -> str:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, 15):
        html = fetch(LIST_URL + ("" if page == 1 else f"&page={page}"))
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for a in soup.find_all("a", href=re.compile(r"^\?pid=\d+")):
            pid = re.search(r"pid=(\d+)", a["href"]).group(1)
            if pid not in pids:
                pids.append(pid)
                new += 1
        if new == 0:
            break
    return pids


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
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    page_text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    exp_el = soup.select_one("div.exp")
    exp_lines = [unicodedata.normalize("NFKC", l.strip()) for l in
                 (exp_el.get_text("\n", strip=True).split("\n") if exp_el else []) if l.strip()]
    has_cart = "カートに入れる" in page_text

    # 価格: 豆のまま(挽き方)のバリエーション価格
    variants = product.get("variants") or []
    whole = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    pool = whole or variants
    prices = [v.get("option_price_including_tax") for v in pool if v.get("option_price_including_tax")]
    price = min(prices) if prices else (product.get("sales_price_including_tax") or None)

    # 重量
    weight = None
    for pat in (r"合計\s*(\d+)\s*g", r"1袋\s*(\d+)\s*g", r"<\s*(\d+)\s*g\s*>"):
        wm = re.search(pat, page_text)
        if wm:
            weight = int(wm.group(1))
            break

    # 焙煎度の既定値(「お店におまかせ ( ミディアム )」)
    default_roast = None
    opts = [v.get("option1_value") for v in variants if v.get("option1_value")]
    if opts:
        dm = re.search(r"お店におまかせ\s*\(\s*([^)\s]+)", unicodedata.normalize("NFKC", opts[0]))
        default_roast = dm.group(1) if dm else None
    roast_hint = "焙煎度を8段階(ライト/シナモン/ミディアム/ハイ/シティー/フルシティー/フレンチ/イタリアン)から選択"
    if default_roast:
        roast_hint += f"(お店におまかせ={default_roast})"

    labels = {}
    for line in exp_lines:
        lm = LABEL_RE.match(line)
        if lm and lm.group(1) not in labels:
            labels[lm.group(1)] = lm.group(2).strip()

    parsed = parse_product(title)
    is_blend = any(k in title.lower() for k in ("ブレンド", "blend", "mix", "ミックス"))
    country = None
    if not is_blend:
        country = origin_from(labels["国"]) if labels.get("国") else None
        country = country or origin_from(title)
        if not country:
            is_blend = True  # 産地名のない銘柄(豆一なごみスペシャル、Cafe Blue等)は自家ブレンド
    if is_blend:
        category, country = "ブレンド", None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        category = "ストレート"
        parsed["origin_source"] = "country_name"
    parsed["origin_country"] = country

    pm = labels.get("生産処理") or labels.get("精選方法")
    processing = normalize_processing_method(pm) if pm else parsed["processing_method"]

    farm_parts = []
    for key, label in (("エリア", "エリア"), ("生産者", "生産者"), ("標高", "標高"), ("品種", "品種")):
        if labels.get(key):
            farm_parts.append(f"{label}: {labels[key]}")
    farm_note = "、".join(farm_parts) or None

    cup = next((l for l in exp_lines if l.startswith("カッピングプロファイル")), None)
    flavor = None
    if cup:
        idx = exp_lines.index(cup)
        flavor = (cup.split(":", 1)[1].strip() if ":" in cup else "") or (exp_lines[idx + 1] if idx + 1 < len(exp_lines) else None)
    if not flavor:
        body = [l for l in exp_lines if not LABEL_RE.match(l) and not l.startswith(("※", "<", "＜", "販売価格"))]
        flavor = " ".join(body[:2])[:160] or None

    stock_status = detect_stock_status(title, structural_out_of_stock=not has_cart)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": category,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_selectable": True,
        "roast_hint": roast_hint,
        "flavor_notes": flavor,
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
    records = []
    seen = set()
    for pid in list_pids():
        rec = build_record(pid)
        if not rec:
            continue
        # 「ゴールデン ICEブレンド」のように同名・同価格・同重量で2つの商品ページが並ぶ重複掲載は1件にする
        key = (rec["raw_name"], rec["price"], rec["weight_g"])
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_mameichirakuizumi.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameichirakuizumi.json に出力しました")


if __name__ == "__main__":
    main()
