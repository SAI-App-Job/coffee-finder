# -*- coding: utf-8 -*-
"""
scrape_sannocoffee.py

山王珈琲焙煎所(https://www.sanno-coffee.jp/、茨城県取手市山王87-1)のコーヒー豆通販の
商品情報を取得する。WordPress + Welcart(有限会社椎名米菓が2023年に開始した自家焙煎事業)。

【店舗発見の経緯】
全国再調査(茨城県・栃木県)の新規発掘で発見。

【取得方法】
商品一覧 /various-products の「定番コーヒー豆」「季節のおすすめコーヒー豆」の2区画から
商品ページのリンクを集め、各ページの「原産地」「内容量」「焙煎度合」と、
サイズ別(100g/200g/300g)の「在庫状態」「価格」を読む。サイズ別に価格が並ぶので
最小重量(多くは100g)を代表にする。挽き方は「コーヒー豆のまま」の価格(挽き方で価格は変わらない)。

【対象】豆のみ。お試し・日常セット、ドリップバッグ、冷めても美味しいセット、まとめ買い(1kg〜)、
ギフト、チョコレート・ナッツ・煎餅は一覧の別区画にあるため対象外。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "山王珈琲焙煎所",
    "url": "https://www.sanno-coffee.jp/",
    "platform": "WordPress + Welcart",
    "address": "茨城県取手市山王87-1",
    "prefecture": "茨城県",
    "robots_txt_status": "許可(User-agent: * は /wp/wp-admin/ のみDisallow)",
    "source_note": "公式サイト(https://www.sanno-coffee.jp/ )の商品一覧 /various-products と各商品ページ、"
                   "/company・/specific-trade-law を2026-10-26に確認。お知らせの最新は2026-09-30。"
                   "100gを代表とし、挽き方は「コーヒー豆のまま」。セット・ドリップバッグ・まとめ買いは除外。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.sanno-coffee.jp"
LIST_URL = f"{BASE_URL}/various-products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 2

SECTION_START = "定番コーヒー豆 "   # 商品一覧の見出し(末尾に空白あり)。ナビの「定番コーヒー豆」と区別する

# 商品ページのタイトルは長いキャッチコピー付きなので、商品名を明示する(キーは投稿ID)
NAME_BY_ID = {
    "2877": "冷めても美味しいJASオーガニック『山王コーヒー』",
    "1931": "ペルー JASオーガニック",
    "2757": "【完全無農薬栽培】エチオピアモカ",
    "2531": "モカマタリ(イエメン)",
    "2535": "ペルー【ゲイシャ】 JASオーガニック",
    "2996": "『ぜうすプラス』",
    "2834": "コロンビア『エメラルドマウンテン』",
    "2770": "コロンビア【チロソ】",
    "2782": "【ゲイシャ】コロンビア サンビクトリノ農園",
    "2612": "最高級マンデリン",
    "2501": "キリマンジャロ ”南十字星(サザンクロス)”",
    "2389": "エチオピア ゲイシャ",
    "2583": "ジャマイカ ブルーマウンテンNo.1",
    "2778": "パナマ【最高級ゲイシャ】 ボケテ エル・パロマール農園",
}
# 産地(原産地欄: 山王コーヒーはグアテマラ・コスタリカ、ぜうすプラスはコロンビア産)
ORIGIN_BY_ID = {
    "2531": "イエメン",
    "2501": "タンザニア",
    "2389": "エチオピア",
    "2583": "ジャマイカ",
    "2612": "インドネシア",
    "2757": "エチオピア",
    "2535": "ペルー",
    "1931": "ペルー",
}
BLEND_IDS = {"2877", "2996"}  # 山王コーヒー(グアテマラ・コスタリカ)、ぜうすプラス(ブレンド)
EXCLUDE_WORDS = ["ドリップ", "セット", "ギフト", "定期"]

ROAST_RE = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def get(url: str) -> str:
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def to_text(page: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    body = html.unescape(re.sub(r"<[^>]+>", "\n", body))
    return re.sub(r"[ \t　]+", " ", re.sub(r"\n\s*\n+", "\n", body))


def collect_product_urls() -> list[str]:
    page = get(LIST_URL)
    start = page.find(SECTION_START)
    end = page.find("まとめ買い（1kg")
    if start < 0 or end < 0:
        raise RuntimeError("商品一覧の区画が見つからない")
    seg = page[start:end]
    urls = []
    for m in re.finditer(r'<a[^>]+href="(https://www\.sanno-coffee\.jp/[^"]+\.php)"[^>]*>(.*?)</a>', seg, re.S):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(m.group(2)))).strip()
        if not title or any(w in title for w in EXCLUDE_WORDS):
            continue
        if m.group(1) not in urls:
            urls.append(m.group(1))
    return urls


def parse_page(url: str) -> dict | None:
    pid = re.search(r"/(\d+)\.php$", url).group(1)
    txt = to_text(get(url))
    origin_field = re.search(r"原産地\n([^\n]+)\n", txt)
    roast_field = re.search(r"焙煎度合\n([^\n]+)\n", txt)
    # サイズ別: 「<名称> 100g」「挽き」...「在庫状態 : 在庫有り」「¥900」
    variants = []
    for m in re.finditer(r"\n([^\n]*?(\d+)\s*[gｇ])\n挽き\n(?:[^\n]+\n)+?在庫状態 : ([^\n]+)\n ¥([\d,]+)\n", txt):
        variants.append((int(m.group(2)), m.group(3).strip(), int(m.group(4).replace(",", ""))))
    if not variants:
        return None
    weight, stock, price = min(variants, key=lambda v: v[0])
    # 説明文: 「香り」の星評価の次の行から価格表の手前まで
    desc_m = re.search(r"香り\n[★☆]+\n(.*?)(?:\n[^\n]*\d+\s*[gｇ]\s+[\d,]+円)", txt, re.S)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    return {
        "id": pid,
        "url": url,
        "title": txt.strip().split("\n")[0].split(" | ")[0],
        "origin_field": origin_field.group(1) if origin_field else None,
        "roast": roast_field.group(1) if roast_field else None,
        "weight": weight,
        "stock": stock,
        "price": price,
        "desc": desc,
    }


def build_record(p: dict) -> dict | None:
    name = NAME_BY_ID.get(p["id"]) or p["title"]
    if any(w in name for w in EXCLUDE_WORDS):
        return None
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if p["id"] in BLEND_IDS:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = ORIGIN_BY_ID.get(p["id"]) or detect_country_name(name) or detect_country_name(p["origin_field"] or "")
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "description"
        parsed = apply_category_hint_fallback(parsed, name)
    rm = ROAST_RE.search(p["roast"] or "")
    roast = rm.group(1) if rm else parsed["roast_level"]
    sold_out = any(w in p["stock"] for w in ["売り切れ", "売切", "なし", "品切", "完売"])
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
        "flavor_notes": p["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": p["price"],
        "weight_g": p["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": p["url"],
    }


def scrape_all_products() -> list[dict]:
    urls = collect_product_urls()
    records = []
    for url in urls:
        time.sleep(REQUEST_INTERVAL_SEC)
        try:
            p = parse_page(url)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {url} ({e})")
            continue
        if not p:
            print(f"[warn] 価格表を解析できず: {url}")
            continue
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sannocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sannocoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
        print("     ", (r["flavor_notes"] or "")[:80])


if __name__ == "__main__":
    main()
