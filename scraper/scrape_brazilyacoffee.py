# -*- coding: utf-8 -*-
"""
scrape_brazilyacoffee.py

自家焙煎珈琲 ブラジル屋(千葉県木更津市文京、Brazilya Coffee Web Shop)の
カラーミーショップ(shop.brazilya.co.jp、独自ドメイン)の商品情報を取得する。

【対象】カテゴリ「コーヒー豆 [ストレート]」(cbid=235812)と「コーヒー豆 [ブレンド]」(cbid=236121)。
除外: 「【インフュージョン コーヒー】純米吟醸 きみさらず」(日本酒に漬け込んだインフューズド)、
ギフト・オリジナル商品(水出しパック、ボトルアイス)・食品&雑貨・器具(別カテゴリ)。
【価格・重量】variants の option1=「1袋の量」(200g/500g)、option2=「コーヒーの状態」(豆のまま/挽き)。
豆のまま×最小重量(200g)の税込価格を採用(500gは5%お得な同一銘柄の大袋)。
【文字コード】EUC-JP。robots.txt: /secure/ と /cart/ のみ禁止(2026-10-26確認)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, ROAST_KEYWORDS

SHOP_INFO = {
    "name": "自家焙煎珈琲 ブラジル屋",
    "url": "https://shop.brazilya.co.jp/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "千葉県木更津市文京3-1-10",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/のみDisallow)",
    "source_note": "カラーミーショップ(https://shop.brazilya.co.jp/)のカテゴリ「コーヒー豆 [ストレート]」「コーヒー豆 [ブレンド]」と"
                   "各商品ページを2026-10-26に確認。住所は公式サイト(https://www.brazilya.co.jp/)の店舗案内。"
                   "200gの豆のまま価格を採用。インフュージョンコーヒー・ギフト・水出しパック・ボトルアイス・器具は除外",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://shop.brazilya.co.jp/"
CATEGORIES = [(235812, "ストレート"), (236121, "ブレンド")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2.0

EXCLUDE_NAME_KEYWORDS = ["インフュージョン", "インフューズド", "ギフト", "セット", "ドリップバッグ", "水出し", "ボトル"]
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
WEIGHT_RE = re.compile(r"(\d+)\s*[gｇ]")
ROAST_LABEL_RE = re.compile(r"(極深煎り|中深煎り|深煎り|中浅煎り|浅煎り|中煎り)")
ROAST_LINE_RE = re.compile(r"^(?:Roast\s*[：:]|焙\s*煎\s*[：:]|【ロースト】)")
SOLD_OUT_RE = re.compile(r"売り切れ|SOLD ?OUT|品切れ|完売|在庫なし|入荷待ち")
SPEC_LINE_RE = re.compile(r"^(?:[・■◆]?\s*表示価格|[・■]?\s*[５5]００ｇ|[・■]?\s*500g|Roast|Roaster|焙\s*煎|焙煎機|Region|Farm|Owner|Altitude|Variety|Grade|PROCESS|Certification|生産|農園|標高|品種|精製|【|型番|BA\d|BD\d)")

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
    out: list[tuple[str, str]] = []
    for cbid, kind in CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0&sort=n" + (f"&page={page}" if page > 1 else "")
            html_text = fetch(url)
            pids = list(dict.fromkeys(re.findall(r'href="\?pid=(\d+)"', html_text)))
            new = [p for p in pids if p not in [x[0] for x in out]]
            if not pids or not new:
                break
            out.extend((p, kind) for p in new)
            if f"page={page + 1}" not in html_text:
                break
            page += 1
    return out


def pick_variant(variants: list[dict]) -> dict | None:
    cands = []
    for v in variants:
        opts = unicodedata.normalize("NFKC", f"{v.get('option1_value') or ''} {v.get('option2_value') or ''}")
        if "豆のまま" not in opts:
            continue
        m = WEIGHT_RE.search(opts)
        cands.append((int(m.group(1)) if m else 10**9, v))
    return min(cands, key=lambda x: x[0])[1] if cands else None


def detect_roast(lines: list[str]) -> str | None:
    """焙煎度の行(Roast：/焙煎：/【ロースト】)から「中煎り」等の表記を取る。無ければ「ハイ」「シティ」等の
    ロースト名、それも無ければ本文中の「フレンチロースト」等の明記を使う。"""
    rl = [l for l in lines if ROAST_LINE_RE.match(l)]
    for l in rl:
        m = ROAST_LABEL_RE.search(l)
        if m:
            return m.group(1)
    for l in rl:
        for kw, label in ROAST_KEYWORDS.items():
            if kw in l:
                return label
    for l in lines:
        for kw, label in ROAST_KEYWORDS.items():
            if kw + "ロースト" in l:
                return label
    return None


def parse_detail(pid: str, kind: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_RE.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1))["product"]
    raw_name = product["name"].strip()
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw_name)).strip()
    if any(k in name for k in EXCLUDE_NAME_KEYWORDS):
        print(f"[skip] {name}")
        return None
    v = pick_variant(product.get("variants", []))
    if v is None:
        return None
    wm = WEIGHT_RE.search(unicodedata.normalize("NFKC", f"{v.get('option1_value')} {v.get('option2_value')}"))
    weight = int(wm.group(1)) if wm else None

    soup = BeautifulSoup(html_text, "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    text = soup.get_text("\n", strip=True)
    j = text.find("販売価格")
    i = text.rfind(raw_name, 0, j) if j > 0 else -1
    block = text[i + len(raw_name):j] if i >= 0 and j > i else ""
    lines = [unicodedata.normalize("NFKC", l.strip()) for l in block.split("\n") if l.strip()]
    roast = detect_roast(lines)
    story = [l for l in lines if not SPEC_LINE_RE.match(l)]
    flavor_notes = " ".join(story)[:200] or None

    parsed = parse_product(name)
    if kind == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            mo = re.search(r"(?:生産国|生 産 国)[】:：]?\s*([^\s\n]+)", unicodedata.normalize("NFKC", block))
            if mo:
                parsed["origin_country"] = mo.group(1)
                parsed["origin_source"] = "description"
    if "semi-washed" in name.lower():
        parsed["processing_method"] = "セミウォッシュド"
    sold_out = bool(SOLD_OUT_RE.search("\n".join(lines)))
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
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": v["option_price_including_tax"],
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, kind in list_product_ids():
        try:
            rec = parse_detail(pid, kind)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗 {pid}: {e}")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_brazilyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_brazilyacoffee.json に出力しました")


if __name__ == "__main__":
    main()
