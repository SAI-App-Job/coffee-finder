# -*- coding: utf-8 -*-
"""
scrape_saitaniya.py

自家焙煎珈琲 サイタニヤ(茨城県那珂郡東海村船場193-1、公式 https://saitaniya.com/)の
Yahoo!ショッピングストア(store.shopping.yahoo.co.jp/cafe-saitaniya、ストア名
「自家焙煎珈琲 サイタニヤ Yahoo!店」)の商品情報を取得する。

【プラットフォーム】
他のYahoo!ショッピング店舗(scrape_mameyanetshop.py 等)と同様、店舗の商品一覧
(/search.html、2ページ目以降は ?page=1,2,...)の Next.js `__NEXT_DATA__` JSON
(props.initialState.bff.searchResults.items.<ページ番号>[1].content.items)に商品名・価格・URLが
埋め込まれている。ページ番号キーはページごとに変わるため、items 辞書の先頭値を使う。
robots.txtでは /search.html のクエリなし・page指定は Disallow 対象外。

【対象商品】
実データ確認済み(2026-10時点、全153件): 1銘柄につき 200g / 300g / 400g / 500g / 1kg の
重量違いが別商品ページ(コード末尾 -3 / -4 / -5 / -10)で並ぶ。最小重量(200g、コード末尾なし)の
ページだけを代表に採用する。Kalita(カリタ)のドリッパー・ろ紙3点は対象外。
ストレート(エチオピア・タンザニア・ルワンダ・インドネシア・グアテマラ・ブラジル等)、
ブレンド(サイタニヤ/キリマン/モカ/リッチビター/オーガニックナチュラル/アメリカン/
エスプレッソ/アイスコーヒー)、デカフェ(グアテマラ)が対象。
重量は商品名の「200g(…)(生豆時)」どおり生豆の状態でのグラム数(焙煎後は約10〜20%目減り)。
焙煎度は購入時に「焙煎度合」オプション(ライト〜イタリアンロースト)で選べる選択式で、
商品説明の「おすすめの焙煎は○○ローストです」を roast_hint(推奨焙煎度)とし、
roast_level は None・roast_selectable は True とする。
在庫は詳細ページの schema.org availability で判定する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲サイタニヤ",
    "url": "https://saitaniya.com/",
    "platform": "Yahoo!ショッピング(自社サイトのカートはYahoo!店 cafe-saitaniya)",
    "address": "茨城県那珂郡東海村船場193-1",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *は/cgi-bin/・/search.htmlの絞り込みクエリ等のみDisallow。"
                          "本スクレイパーが使う/search.html・?page=N は制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/cafe-saitaniya"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\s*(?:\(|$)", re.IGNORECASE)
ROAST_REC_PATTERN = re.compile(r"おすすめの焙煎は([^\s。]+?)です")

# コード(商品ページ名の先頭部分) -> (整形名, ブレンドか, 産地国)
NAMES = {
    "af001": ("エチオピア シダモ", False, "エチオピア"),
    "af002": ("キリマンジャロAA", False, "タンザニア"),
    "af003": ("ルワンダ スカイヒル コプロカWS", False, "ルワンダ"),
    "af005": ("タンザニア KIBO AA", False, "タンザニア"),
    "af006": ("モカ イリガチャフ G2 ウォッシュド", False, "エチオピア"),
    "as002": ("マンデリンG1", False, "インドネシア"),
    "as003": ("ゴールデン マンデリン", False, "インドネシア"),
    "as004": ("トラジャ カロシ", False, "インドネシア"),
    "as005": ("モカ マタリNo.9", False, "イエメン"),
    "as006": ("ベトナム アラビカ グリーン ダラット", False, "ベトナム"),
    "as009": ("トラジャ ランテカルア 有機JAS栽培", False, "インドネシア"),
    "ca001": ("グアテマラSHB", False, "グアテマラ"),
    "ca002": ("オーガニック グアテマラ 有機 アティトラン", False, "グアテマラ"),
    "ca003": ("ホンジュラスHG", False, "ホンジュラス"),
    "ca024": ("ハイチ ゾンビ デザート【数量限定】", False, "ハイチ"),
    "ca025": ("エルサルバドル マラカラ ブルボン SHG", False, "エルサルバドル"),
    "dg001": ("デカフェ グアテマラ", False, "グアテマラ"),
    "sa001": ("コロンビア エクセルソ", False, "コロンビア"),
    "sa002": ("ペルー チャンチャマヨ G1", False, "ペルー"),
    "sa003": ("サントスNo.2 17/18", False, "ブラジル"),
    "sa021": ("オーガニック コロンビア ウィラ 有機栽培", False, "コロンビア"),
    "sa022": ("オーガニック ブラジル", False, "ブラジル"),
    "si001": ("サイタニヤ ブレンド", True, None),
    "si002": ("キリマン ブレンド", True, None),
    "si003": ("アメリカン コーヒー", True, None),
    "si004": ("モカ ブレンド", True, None),
    "si005": ("リッチビター ブレンド", True, None),
    "si006": ("オーガニック ナチュラル ブレンド", True, None),
    "si007": ("エスプレッソ", True, None),
    "si008": ("アイス コーヒー", True, None),
}


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for page in range(0, 20):
        url = f"{BASE_URL}/search.html" + (f"?page={page}" if page else "")
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
            data = json.loads(m.group(1))
            page_items = list(data["props"]["initialState"]["bff"]["searchResults"]["items"].values())[0][1]["content"]["items"]
        except Exception:
            break
        if not page_items:
            break
        items.extend(page_items)
    return items


def weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    v = float(m.group(1))
    return int(v * 1000) if m.group(2).lower() == "kg" else int(v)


def fetch_detail(url: str) -> dict:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
        return {"in_stock": True, "notes": None, "roast_hint": None, "decaf_process": None}
    text = resp.content.decode("utf-8", "replace")
    dm = re.search(r'og:description" content="([^"]*)"', text)
    notes = None
    roast_hint = None
    decaf_process = None
    if dm:
        desc = html.unescape(dm.group(1)).replace("<br>", "\n")
        rm = ROAST_REC_PATTERN.search(desc)
        if rm:
            roast_hint = rm.group(1)
        lines = [l.strip() for l in desc.split("\n") if l.strip()]
        lines = [l for l in lines if not re.match(r"^(おすすめの焙煎|生豆の状態|宅配便|ご注文確認画面|[＊★*])", l)]
        notes = " ".join(lines)[:400] or None
        if "マウンテンウォータープロセス" in desc:
            decaf_process = "マウンテンウォータープロセス"
    in_stock = "schema.org/OutOfStock" not in text and "schema.org/SoldOut" not in text
    return {"in_stock": in_stock, "notes": notes, "roast_hint": roast_hint, "decaf_process": decaf_process}


def pick_representatives(items: list[dict]) -> list[tuple[str, dict]]:
    """コード単位で最小重量の商品を代表に選ぶ。"""
    best: dict[str, tuple[int, dict]] = {}
    for it in items:
        title = (it.get("name") or "").strip()
        url = (it.get("url") or "").split("?")[0]
        stem = url.rsplit("/", 1)[-1].replace(".html", "").split("-")[0]
        if stem not in NAMES or "コーヒー豆" not in title:
            continue
        w = weight_g(title)
        if w is None:
            continue
        if stem not in best or w < best[stem][0]:
            best[stem] = (w, it)
    return [(stem, best[stem][1]) for stem in NAMES if stem in best]


def build_record(stem: str, item: dict) -> dict:
    name, is_blend, origin = NAMES[stem]
    title = item["name"]
    url = (item.get("url") or "").split("?")[0]
    detail = fetch_detail(url)

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "description"
        else:
            d = detect_country_name(name)
            if d and not parsed["origin_country"]:
                parsed["origin_country"] = d
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_selectable": True,  # 実データ確認済み: 購入時に「焙煎度合」オプションで選択
        "roast_hint": detail["roast_hint"],
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "decaf_process": detail["decaf_process"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight_g(title),
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    items = fetch_list_items()
    print(f"[info] 一覧 {len(items)}件取得")
    return [build_record(stem, it) for stem, it in pick_representatives(items)]


def main():
    records = scrape_all_products()
    with open("data_saitaniya.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_saitaniya.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_hint"], r["stock_status"])


if __name__ == "__main__":
    main()
