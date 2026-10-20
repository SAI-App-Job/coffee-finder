# -*- coding: utf-8 -*-
"""
scrape_orioncoffee.py

オリオン珈琲焙煎所(福岡市東区箱崎3-2-23、公式サイト www.orioncoffee.jp、
「ご注文を受けてからの焙煎」の自家焙煎店)のネットショップの商品情報を取得する。
カラーミーショップ(orioncoffee.shop-pro.jp)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品検索(?mode=srh)は計18件(ブレンド4・ストレート14)で、
すべてコーヒー豆。ドリップバッグ・セット等は無いため全件を対象とする。
 - ブレンド: オリオンブレンド・はこざきブレンド・ほろにがブレンド・すっきりブレンド
 - ストレート14件(限定豆・復活豆を含む)。「デカフェ・メキシコ」はカフェインレス。

【重量・価格について】
ショップ共通の案内文に「煎りたてのコーヒー豆をお送りします(生豆200gを焙煎します。
煎り上がりは重さが15〜20%減少します)」とあり、表示価格は生豆200g分の価格である。
重量は200gとして登録し、注記を unit_note に残す(焙煎後の実重量は約160〜170g)。

【焙煎度】
商品ページのパンくず(ストレートは焙煎度ごとのカテゴリ)または本文の焙煎度表記を採用する。
ブラジル・ショコラ等は本文の「シティロースト深め」「シティロースト浅め」をそのまま用いる。

【在庫】
カートフォーム(購入数欄)がある商品は販売中、無ければ完売とする(現状は全件販売中)。

【robots.txt】
Disallow: /secure/, /cart/ のみ(他は特定ボットのみ禁止)。商品ページ・検索は対象外。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "オリオン珈琲焙煎所",
    "url": "https://orioncoffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "福岡県福岡市東区箱崎3丁目2-23",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-10-20確認。Disallowは/secure/・/cart/のみ。識別可能なUser-Agentを使用)",
    "source_note": "ネットショップ(https://orioncoffee.shop-pro.jp/)の全商品検索・各商品ページを2026-10-20に確認。公式サイト https://www.orioncoffee.jp/ に住所『福岡市東区箱崎３丁目２－２３』、営業時間・定休日、『ご注文を受けてからの焙煎を行っています』の記載あり。価格は『生豆200gを焙煎します(焙煎後は15〜20%減)』の生豆200g基準のため、重量は200gで登録。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://orioncoffee.shop-pro.jp/"
SEARCH_URL = BASE_URL + "?mode=srh&cid=&keyword=&page={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
WEIGHT_G = 200
UNIT_NOTE = "生豆200g基準(焙煎後は15〜20%減)"

ROAST_WORDS = ("フルシティロースト", "シティロースト", "ハイロースト", "ミディアムロースト", "フレンチロースト")
ORIGIN_OVERRIDES = {
    "アマレロ・ブルボン": "ブラジル",
    "マンデリンG1": "インドネシア",
    "モカシダモG2": "エチオピア",
    "パラダイス・プレミアム": "パプアニューギニア",
    "カロシ・トラジャ": "インドネシア",
    "キリマンジャロ": "タンザニア",
    "デカフェ・メキシコ": "メキシコ",
    "〈限定豆〉アルティプラノス農園": "ニカラグア",
    "〈限定豆〉イルガチェフェ G4": "エチオピア",
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, 6):
        html_text = fetch(SEARCH_URL.format(page=page))
        found = [p for p in dict.fromkeys(re.findall(r"\?pid=(\d+)", html_text)) if p not in pids]
        # ランキング欄の商品が全ページに出るため、新規が無いページで打ち切る
        if not found:
            break
        pids.extend(found)
        time.sleep(REQUEST_INTERVAL)
    return pids


def parse_detail(pid: str) -> dict | None:
    soup = BeautifulSoup(fetch(f"{BASE_URL}?pid={pid}"), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    head_i = text.find("TOP\n>")
    price_i = text.find("販売価格")
    pm = re.search(r"販売価格\s*([\d,]+)円", text)
    if head_i < 0 or price_i < 0 or not pm:
        return None
    seg = [ln.strip() for ln in text[head_i:price_i].split("\n") if ln.strip()]
    # seg: TOP, >, ストレート|ブレンド, [>, 焙煎度カテゴリ], 商品名, 説明...
    crumbs = []
    i = 2
    crumbs.append(seg[i])
    i += 1
    cat_roast = None
    if i < len(seg) and seg[i] == ">":
        cat_roast = seg[i + 1]
        i += 2
    name = soup.title.get_text(strip=True).rsplit(" - ", 1)[0] if soup.title else seg[i]
    desc_lines = seg[i + 1:]
    return {
        "pid": pid,
        "name": name,
        "kind": crumbs[0],
        "cat_roast": cat_roast,
        "desc_lines": desc_lines,
        "price": int(pm.group(1).replace(",", "")),
        "purchasable": "購入数" in text,
    }


def build_record(d: dict) -> dict:
    name = d["name"]
    desc = " ".join(d["desc_lines"])
    # 本文中の焙煎度表記(深め/浅めを含む)を優先し、無ければパンくずのカテゴリを使う
    roast = d["cat_roast"]
    rm = re.search(r"(フルシティロースト|シティロースト深め|シティロースト浅め|シティロースト|ハイロースト)", desc)
    if rm:
        roast = rm.group(1)
    if d["kind"] == "ブレンド":
        roast = rm.group(1) if rm else roast
    parsed = parse_product(name)
    if d["kind"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "デカフェ" if "デカフェ" in name else "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        if name in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[name]
            parsed["origin_source"] = "raw_name"
    sold_out = not d["purchasable"]
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
        "flavor_notes": desc[:300] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": d["price"],
        "weight_g": WEIGHT_G,
        "unit_note": UNIT_NOTE,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={d['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_pids():
        try:
            d = parse_detail(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if d:
            records.append(build_record(d))
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_orioncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_orioncoffee.json に出力しました")


if __name__ == "__main__":
    main()
