# -*- coding: utf-8 -*-
"""
scrape_kibinokunicoffee.py

吉備の国珈琲焙煎所(岡山県岡山市北区表町1丁目7-15 パークスクエアSHOWA 1F)の楽天市場店
(www.rakuten.co.jp/kibinokuni-coffee)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。
(docsで直営オンラインショップ kibico.net の商品ページがJS描画(Square Online)を理由に見送りとなっていた店を、
楽天市場店で再発見したもの。直営サイトは楽天店とリンクしており、品目は楽天店のほうが静的に取得できる。)

【対象商品について】
楽天のショップ内検索(search.rakuten.co.jp/search/mall/?sid=361302、全20件、2026-11-02確認)のうち、
コーヒー豆の単品13件(ブレンド3・ストレート10)。除外: ドリップバッグ(dps-1, dppremiumset)、スペシャルティコーヒー
ギフトセット/お好み4タイプセット(sm-01g, sm-02, sm-05g)、焙煎度比較体験セット(set-261r)、水出しパック(mizudashipackb8)。
各銘柄は100g(お試し)/200g/300g/500gのSKUがあり、最小重量の100gの価格(税込・メール便送料無料表記)を代表とする。
すべてご注文後に焙煎するオーダー焙煎で、焙煎度ロースト1〜8を購入時に選べる(roast_selectable)。ブレンドは「基本ロースト」
(スペシャルブレンド=5シティ、HAPPY=6フルシティ、昭和=7フルシティ)を焙煎度として登録する。
パナマ ゲイシャ(a-002)は商品名に「近日入荷」とあるが、SKUは購入可能(isSoldOut=false, itemprop=InStock)のため販売中として扱う。
ワイルド コピルアク(a-001)は産地の記載が商品ページに無いため origin は未設定。
在庫は itemprop="availability"。販売業者: 吉備の国珈琲焙煎所(岡山市北区表町1丁目7-15 パークスクエアSHOWA 1F)。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "吉備の国珈琲焙煎所",
    "url": "https://www.rakuten.co.jp/kibinokuni-coffee/",
    "platform": "楽天市場",
    "address": "岡山県岡山市北区表町1丁目7-15 パークスクエアSHOWA 1F",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可とみなす(2026-11-02確認。www.rakuten.co.jp / item.rakuten.co.jp / search.rakuten.co.jp のrobots.txtは検索系パラメータ・一部パス等のみ禁止で、商品ページ・sid検索は対象外)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/kibinokuni-coffee/)のショップ内検索(全20件)と各商品ページ、公式サイト(https://www.kibinokuni.a-zone-t.net/)の店舗案内を2026-11-02に確認。楽天の新商品は2026/08/18。公式サイトは約70種類の品揃えと記載があるが、楽天店掲載の豆は13銘柄(各100gを代表)。ご注文後に焙煎するオーダー焙煎(ロースト1〜8を選択)。店舗は表町(火曜定休)",
    "last_verified_at": "2026-11-02",
}

SHOP_ID = "kibinokuni-coffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, 産地(Noneはブレンド/不明), 基本焙煎度(Noneは選択式のみ), 風味キャッチ)
ITEMS = [
    ("d-5011", "吉備の国 スペシャルブレンド", None, "シティロースト", "毎日の一杯に選ばれている定番ブレンド。やさしい味と香りながらしっかりした存在感、さわやかなアフターテイスト", True),
    ("happyblend", "HAPPYブレンド", None, "フルシティロースト", "香りよく奥行きのある苦味とふんわりした甘み、絶妙バランスのコクと旨味", True),
    ("showablend", "昭和ブレンド", None, "フルシティロースト", "深煎りの昭和ブレンド", True),
    ("d-501s", "ブラジル サントス No.2", "ブラジル", None, None, False),
    ("d-502", "コロンビア スプレモ", "コロンビア", None, None, False),
    ("d-503", "グアテマラ SHB", "グアテマラ", None, None, False),
    ("d-504", "タンザニア AA", "タンザニア", None, None, False),
    ("d-505", "マンデリン G1", "インドネシア", None, None, False),
    ("d-506", "エチオピア モカ", "エチオピア", None, "甘い香りのやさしいコーヒー。浅煎でフルーティさ、深煎りで甘さ", False),
    ("s-1000-1", "ホンジュラス セレクトマウンテン SHG", "ホンジュラス", None, "毎日飲みたくなる、やさしくバランスの良い味わい", False),
    ("a-003", "ブルーマウンテン No.1 ジャマイカ S17", "ジャマイカ", None, "雑味のない澄んだ味わい、やさしいコクとなめらかさ", False),
    ("a-001", "ワイルド コピルアク", None, None, None, False),
    ("a-002", "パナマ エスメラルダ農園 ゲイシャ プライベートコレクション", "パナマ", None, "フローラルなアロマと柑橘系の上質な甘み", False),
]


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


def build_record(code, name, origin, roast, catch, is_blend):
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    price = None
    skus = extract_skus(html_text)
    if skus:
        for s in skus:
            vals = unicodedata.normalize("NFKC", " ".join(s.get("selectorValues") or []))
            if re.search(r"(?<!\d)100g", vals):
                price = int(s["taxIncludedPrice"])
                break
    else:
        m = PRICE_PATTERN.search(html_text)
        price = int(m.group(1)) if m else None
    if price is None:
        print(f"[warn] 価格取得失敗: {code} {name}")
        return None
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "shop_attribute" if origin else None
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
        "roast_hint": roast,
        "roast_selectable": True,
        "flavor_notes": catch,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def main():
    records = []
    for i, item in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(*item)
        if rec:
            records.append(rec)
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kibinokunicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kibinokunicoffee.json に出力しました")


if __name__ == "__main__":
    main()
