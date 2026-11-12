# -*- coding: utf-8 -*-
"""
scrape_kohikobohiguchi.py

珈琲工房ひぐち(有限会社ひぐち、岐阜県各務原市那加桜町1丁目72-1〈桜町本店〉、公式 cafe-higuchi.jp)の
楽天市場店「自家焙煎 珈琲工房ひぐち」(www.rakuten.co.jp/cafe-higuchi)の商品情報を取得する。
楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店を採用した理由】
公式サイトの商品紹介(cafe-higuchi.jp/item-list/)は楽天市場店へ誘導しており、独自ECは無い。通販は楽天市場店のみ
(ふるさと納税返礼品ページは対象外)。

【店舗数について】
公式サイトの店舗情報は桜町本店・アピタ各務原店・北一色店(焙煎工場)・マーサ21店の4店舗(岐阜県内)で、11店舗未満。

【対象商品について】
ショップカテゴリ「シングルオリジン」(c/0000000160、全36件)と「ブレンドコーヒー豆」(c/0000000161、全8件)の
一覧で全商品を確認(各国別・COE・ゲイシャ等のサブカテゴリの商品は親カテゴリの一覧に全て含まれることを確認、2026-11-01)。
除外: ギフト缶・ギフトセット(コピルアック 100g/160g缶入り・パナマ エスメラルダ ギフト・ブルーマウンテン80g×2本ギフト)、
コーヒー豆セット、ドリップバッグ、アイスコーヒーリキッド、カフェオレベース、水出し、器具、ギフトカード。
各銘柄は商品ページの SKU(重量 × 挽き方)のうち、豆のままの最小重量(通常100g、50gがある銘柄は100g)を代表とし、
税込価格(taxIncludedPrice)を採用する。在庫は商品ページの itemprop="availability"(商品単位)で、
売り切れ表示の銘柄(COE等の限定ロット)は完売として出力する。
産地は商品名の国名(商品属性「原料原産地」は産地名や複数国の混在があるため使わない)。ブレンドは産地なし。
焙煎度は商品名に単一表記のあるもの(中深煎・中煎・深煎)のみ roast_level にし、無いものは商品属性「ロースト度合い」を
roast_hint にする。品種・標高・規格は商品の仕様欄から farm_note にする。
販売業者: 有限会社ひぐち 岐阜県岐阜市北一色9-22-2(楽天の会社概要)。実店舗の住所は桜町本店を採用。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "珈琲工房ひぐち",
    "url": "https://www.rakuten.co.jp/cafe-higuchi/",
    "platform": "楽天市場",
    "address": "岐阜県各務原市那加桜町1丁目72-1",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可とみなす(2026-11-01確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/cafe-higuchi/)のカテゴリ「シングルオリジン」「ブレンドコーヒー豆」と各商品ページ(SKU情報)を2026-11-01に確認。"
                   "公式(cafe-higuchi.jp)の店舗情報は4店舗(桜町本店・アピタ各務原店・北一色店・マーサ21店)、商品は楽天へ誘導。2026-11のお知らせあり",
    "last_verified_at": "2026-11-01",
}

SHOP_ID = "cafe-higuchi"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')

# (商品コード, 商品名, 産地(Noneはブレンド), 焙煎度(商品名に単一表記があるもの))
ITEMS = [
    ("10000737", "ブラジル パッセイオ農園 ムンドノーボ", "ブラジル", "中深煎り"),
    ("1562799", "ブラジル パッセイオ農園 ブルボン", "ブラジル", "中深煎り"),
    ("1395691", "ブラジル COE#17 サンジュダスタデウ農園", "ブラジル", None),
    ("10000743", "エルサルバドル マラカラ農園", "エルサルバドル", None),
    ("coe000001", "エルサルバドル COE2024 #9 エル マナンシャル農園", "エルサルバドル", None),
    ("10000783", "エチオピア イルガチェフェ G-1", "エチオピア", None),
    ("coe000005", "エチオピア COE2024 #14 アザレチュ農園", "エチオピア", None),
    ("10000878", "グァテマラ サン ミゲル", "グアテマラ", "中深煎り"),
    ("100008780", "グァテマラ マリアージュ", "グアテマラ", "中深煎り"),
    ("10000879", "グァテマラ グラナダ", "グアテマラ", "中深煎り"),
    ("10001192", "グァテマラ ゲイシャ フロレンシア農園", "グアテマラ", None),
    ("10001373", "グァテマラ アンティグア ゲイシャ ブエナビスタ農園", "グアテマラ", None),
    ("1556293", "グァテマラ エル インヘルト ウノ農園 パカマラ", "グアテマラ", "中深煎り"),
    ("1556294", "グァテマラ エル インヘルト ウノ パカマラ オークションロット 2022", "グアテマラ", "中深煎り"),
    ("1562798", "グァテマラ COE2025 #11 シエラ・ロハ農園 ゲイシャ", "グアテマラ", "中深煎り"),
    ("coe000002", "グァテマラ COE2024 #3 ラ・シーマ農園", "グアテマラ", None),
    ("10000880", "コロンビア クラシック ウィラ スプレモ", "コロンビア", None),
    ("10001169", "ホンジュラス COE2023 #20 ラ・ペニャ農園", "ホンジュラス", None),
    ("coe000003", "コスタリカ COE2023 #28 ラデア アレッシア農園", "コスタリカ", None),
    ("coe000004", "ニカラグア COE2025 #12 エルポステ農園", "ニカラグア", None),
    ("10000965", "パナマ エスメラルダ農園 ゲイシャ エル・ベロ プライベートコレクション", "パナマ", "中煎り"),
    ("10001038", "パナマ エスメラルダ ゲイシャ ハラミージョ 2023 プライベートコレクション", "パナマ", "中煎り"),
    ("1380884", "ジャマイカ ブルーマウンテン No.1", "ジャマイカ", "中煎り"),
    ("1380950", "タンザニア キリマンジャロ モンデュール AA", "タンザニア", "中深煎り"),
    ("1396152", "タンザニア キリマンジャロ AA モンデュール 深煎", "タンザニア", "深煎り"),
    ("1380967", "インドネシア マンデリン G1 トバコ", "インドネシア", "中深煎り"),
    ("1380968", "インドネシア マンデリン トバコ 深煎", "インドネシア", "深煎り"),
    ("1396163", "インドネシア マンデリン アチェ", "インドネシア", "中深煎り"),
    ("1396179", "イエメン クラシック モカマタリ", "イエメン", "中煎り"),
    ("10001190", "ブルンジ ココカ ホラママ", "ブルンジ", "中深煎り"),
    ("gesha-4", "パプアニューギニア ゲイシャ ゴルブラン農園", "パプアニューギニア", None),
    ("1562796", "メキシコ カフェインレス デカフェ 有機JAS", "メキシコ", "中深煎り"),
    ("1383255", "ひぐちブレンド", None, "中深煎り"),
    ("1383382", "ひぐちモカブレンド", None, "中深煎り"),
    ("1383436", "カリブの爽風 ブレンド", None, None),
    ("1396087", "ひぐちストロングブレンド", None, "深煎り"),
    ("1396091", "ひぐちフレンチローストブレンド", None, "深煎り"),
    ("1396095", "ひぐちイタリアンローストブレンド", None, "深煎り"),
    ("1396108", "アイスコーヒーブレンド", None, "深煎り"),
    ("10001181", "ハロウィーンブレンド", None, None),
]

SPEC_LABELS = ("品種", "標高", "規格")


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def extract_skus(html_text: str) -> list[dict]:
    """ページに埋め込まれた "sku":[...] のJSON配列を括弧対応で切り出す。"""
    i = html_text.find('"sku":[')
    if i < 0:
        return []
    start = i + len('"sku":')
    depth, in_str, esc = 0, False, False
    for k in range(start, len(html_text)):
        ch = html_text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html_text[start:k + 1])
    return []


def pick_sku(skus: list[dict]):
    """豆のまま(挽き方の選択肢が「豆のまま」)のSKUから、100gがあれば100g、無ければ最小重量を選ぶ。"""
    cands = []
    for s in skus:
        sel = [unicodedata.normalize("NFKC", v) for v in (s.get("selectorValues") or [])]
        if not any(v.startswith("豆のまま") for v in sel):
            continue
        wm = next((re.fullmatch(r"(\d+)g", v) for v in sel if re.fullmatch(r"(\d+)g", v)), None)
        if not wm:
            continue
        cands.append((int(wm.group(1)), s))
    if not cands:
        return None
    for w, s in cands:
        if w == 100:
            return w, s
    return min(cands, key=lambda c: c[0])


def build_record(code: str, name: str, origin: str | None, roast: str | None) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    picked = pick_sku(extract_skus(html_text))
    if picked is None:
        print(f"[warn] 豆のままSKUなし: {code} {name}")
        return None
    weight, sku = picked
    price = int(sku["taxIncludedPrice"])
    attrs = {a["title"]: a.get("value") for a in sku.get("attributes", [])}
    specs = {sp["label"]: sp["value"] for sp in sku.get("specs", []) if sp.get("label") in SPEC_LABELS}
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name"

    roast_attr = attrs.get("ロースト度合い")
    roast_hint = None if roast else (re.sub(r"\s*/\s*|\s+", "・", roast_attr) if roast_attr else None)
    farm = " / ".join(f"{k}: {specs[k]}" for k in SPEC_LABELS if specs.get(k)) or None
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
        "roast_hint": roast_hint,
        "flavor_notes": None,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, (code, name, origin, roast) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(code, name, origin, roast)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kohikobohiguchi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kohikobohiguchi.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
