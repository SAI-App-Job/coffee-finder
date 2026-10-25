# -*- coding: utf-8 -*-
"""
scrape_hitsujicoffee.py

自家焙煎ひつじcoffee(東京都中野区江原町1-28-6、店主: 鈴木 尚、公式 https://www.hitsuji-coffee.jp/)の
Yahoo!ショッピング店(store.shopping.yahoo.co.jp/hitsuji-coffee)の商品情報を取得する。
(公式サイトは xaas3 カートの自社EC。同じ豆を扱うが、Yahoo!店の方が商品ページ・在庫表示が取得しやすいため
Yahoo!店を採用した。)

【プラットフォームについて】
店舗の商品一覧(/search.html、2ページ目以降は ?page=N)は Next.js の `__NEXT_DATA__` JSON に商品名・価格・URLが
埋め込まれている(scrape_frigoles.py と同方式)。実データ確認済み(2026-10-25): 101件(30+30+30+11件)。
商品詳細ページの `item.applicablePrice`(税込)・`item.stock.isAvailable`(在庫)・`item.information`(説明)を使う。

【対象商品について】
Yahoo!店は同じ銘柄を「200g / 300g / 400g」の別商品(商品コード hc-s-NNN-重量 / hc-b-NNN-重量)として並べている。
自家焙煎の豆単品(ストレート hc-s-*、ブレンド hc-b-*)のみを対象とし、銘柄ごとに最小重量の商品を代表とする。
(100g設定は無く最小は200g。ニカラグア アナエロビックハニーは hc-s-038(300g)と hc-s-040(400g)で別コードだが
同一銘柄のため hc-s-038 に統合。)
除外: 「今週の焙煎コーヒー豆」(hc-kongetsu-*。hc-s-005 と同一銘柄の週替わり告知商品)、
挽き済み(hc-sk-*)、おためし/お試しセット(hc-o-*)、自家焙煎コーヒーセット(hc-set-* / hc-guate-*)、
布フィルター・ペーパーフィルター等の器具(hc-f-*)。
購入時に「豆のまま」/「店主おまかせ挽き」等を選べる商品は豆のまま価格(同額)。価格は税込(8%)・送料無料。
在庫は商品ページの `stock.isAvailable`。品切れの商品も品切れとして残す。

【robots.txt】
store.shopping.yahoo.co.jp/robots.txt は /*/search.html?strcid= 等の特定クエリのみ禁止(2026-10-25確認)。
本スクリプトは search.html の page 指定のみ(禁止クエリなし)と商品ページを取得し、識別UA・3秒間隔で取得する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "自家焙煎ひつじcoffee",
    "url": "https://store.shopping.yahoo.co.jp/hitsuji-coffee/",
    "platform": "Yahoo!ショッピング",
    "address": "東京都中野区江原町1-28-6",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可とみなす(2026-10-25確認。store.shopping.yahoo.co.jp/robots.txtは search.html の strcid/brandid/spec/pt/pf 等のクエリのみ禁止。page指定のみ使用)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/hitsuji-coffee/)の一覧・商品ページを2026-10-25に確認。"
                   "公式サイト https://www.hitsuji-coffee.jp/shop.html と info.html(特定商取引法)に〒165-0023 東京都中野区江原町1-28-6・営業時間10:00〜17:00・定休日 月・土・日曜日。"
                   "公式は自社EC(xaas3)も運営するが、商品ページの取得しやすいYahoo!店を採用",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/hitsuji-coffee"
LIST_URLS = [f"{BASE_URL}/search.html"] + [f"{BASE_URL}/search.html?page={n}" for n in (1, 2, 3)]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 3
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
CODE_PATTERN = re.compile(r"hc-(s|b)-(\d{3})-(\d+)\.html$")

# 同一銘柄が別コードで並ぶもの(代表コードへ統合)
ALIAS = {"s040": "s038"}

# 銘柄コード -> (表示名, 産地(ブレンドはNone), 焙煎度の呼称)
# 名称・焙煎度は商品タイトル/説明文(「中煎り珈琲豆」等)より
BEANS = {
    "s001": ("マンデリン ビンタンリマ", "インドネシア", "中深煎り"),
    "s002": ("モカ イルガチェフェ", "エチオピア", "中煎り"),
    "s004": ("グアテマラSHBアンティグア", "グアテマラ", "中煎り"),
    "s005": ("コロンビア マグダレナ スプレモ(SUP)", "コロンビア", "中深煎り"),
    "s006": ("タンザニア ディープブルー キゴマAA", "タンザニア", "中煎り"),
    "s008": ("ホンジュラスSHGセレクトマウンテン", "ホンジュラス", "中煎り"),
    "s011": ("ブラジル プレミアムショコラ", "ブラジル", "中深煎り"),
    "s015": ("ケニアAAマサイ", "ケニア", "深煎り"),
    "s023": ("モカ イルガチェフェ コチャレ ナチュラル", "エチオピア", "中煎り"),
    "s030": ("グアテマラSHBアンティグア", "グアテマラ", "中深煎り"),
    "s034": ("グアテマラ ファンシーサンタロッサSHB", "グアテマラ", "中煎り"),
    "s036": ("ブラジル ヴィオレッタ", "ブラジル", "中煎り"),
    "s037": ("モカ グジ ゲイシャジャスミン", "エチオピア", "中煎り"),
    "s038": ("ニカラグア ロス アルティプラノス ジャバニカ アナエロビックハニー", "ニカラグア", "中浅煎り"),
    "s042": ("モカ シダモ", "エチオピア", "中煎り"),
    "s043": ("マンデリン ミトラ", "インドネシア", "中深煎り"),
    "s044": ("モカ レケンプティ ナチュラル", "エチオピア", "中煎り"),
    "b001": ("ひつじブレンド・コリデール", None, "中深煎り"),
    "b002": ("さわやかブレンド", None, "中浅煎り"),
    "b003": ("黒ひつじブレンド", None, "深煎り"),
    "b004": ("ソフィア・ブレンド", None, "中煎り"),
}


def fetch_list_items() -> list[dict]:
    items, seen = [], set()
    for url in LIST_URLS:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        time.sleep(CRAWL_DELAY_SECONDS)
        if not m:
            continue
        data = json.loads(m.group(1))
        groups = (((data["props"].get("initialState") or {}).get("bff") or {}).get("searchResults") or {}).get("items") or {}
        for entries in groups.values():
            for entry in entries:
                content = entry.get("content") or {}
                if isinstance(content.get("items"), list):
                    for i in content["items"]:
                        if "name" in i and i["url"] not in seen:
                            seen.add(i["url"])
                            items.append(i)
    return items


def fetch_detail(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
    item = json.loads(m.group(1))["props"]["pageProps"].get("item") or {}
    info = html.unescape(item.get("information") or "")
    info = re.sub(r"<br\s*/?>", "\n", info)
    # 「検索用」「時期用」のSEO文言以降を落とす
    info = re.split(r"検索用[:：]", info)[0]
    desc = re.sub(r"\s+", " ", info).strip()
    return {
        "price": item.get("applicablePrice"),
        "available": bool((item.get("stock") or {}).get("isAvailable", True)),
        "desc": desc or None,
    }


def pick_representatives(items: list[dict]) -> dict:
    best = {}
    for it in items:
        m = CODE_PATTERN.search(it["url"].split("?")[0])
        if not m:
            continue
        key = ALIAS.get(m.group(1) + m.group(2), m.group(1) + m.group(2))
        weight = int(m.group(3))
        if key not in best or weight < best[key][0]:
            best[key] = (weight, it["url"].split("?")[0])
    return best


def build_record(key: str, weight: int, url: str) -> dict:
    if key not in BEANS:
        raise KeyError(f"未登録の銘柄コード: {key}")
    base, origin, coarse = BEANS[key]
    time.sleep(CRAWL_DELAY_SECONDS)
    detail = fetch_detail(url)
    name = f"{base} {coarse}"
    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin in name else "description"
        parsed = apply_category_hint_fallback(parsed, name)
    desc = detail["desc"][:400] if detail["desc"] else None
    out = not detail["available"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": coarse,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    reps = pick_representatives(fetch_list_items())
    records = []
    for key in sorted(reps):
        weight, url = reps[key]
        try:
            records.append(build_record(key, weight, url))
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"[warn] 取得失敗: {key} {url} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hitsujicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hitsujicoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
