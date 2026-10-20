# -*- coding: utf-8 -*-
"""
scrape_tsujimotocoffee.py

辻本珈琲(TSUJIMOTOcoffee、株式会社すてきなじかん、大阪府和泉市春木町1156-1)の公式オンラインショップ
(tsujimoto-coffee.com、フューチャーショップ)のコーヒー豆の商品情報を取得する。

【販売先について】
楽天市場店(www.rakuten.co.jp/tsujimoto/)にも出店しているが、公式オンラインショップの方が
スペシャルティ・グランクリュ(COE入賞ロット等)・デカフェ・ブレンドと品目が揃っているため、公式ショップを採用。

【実店舗・自家焙煎の根拠】
https://tsujimoto-coffee.com/brand/real-shop/ に「TSUJIMOTO coffee SHOP 〒594-1141 大阪府和泉市春木町1156-1」
「厳選した世界各国のスペシャルティコーヒー豆を店内で焙煎し、煎りたて挽きたて淹れたてを提供」
「自家焙煎した新鮮なコーヒー豆を多数ご用意しております」と記載。販売者は特商法表示(/p/about/terms)で
株式会社すてきなじかん、所在地 和泉市春木町1156-1。実店舗は1店舗(他は卸先のカフェ)。

【対象商品】
カテゴリ「コーヒー豆・粉」(/c/all/beans)の単品(スペシャルティ・グランクリュ・デカフェ・ブレンド・
レギュラー)。1銘柄につき最小重量の豆のままの価格を代表にする(100g対応の銘柄は100g、200gからの銘柄は200g、
一部は500g)。除外: ドリップバッグ・ギフト/飲み比べセット・福袋・生豆・お試し(50g×2)・
粉のみのアイス用ポット用パック(カリビアンブレンド50g/80g)・1kg以上(200g×5袋、業務用1.5kg/6kg)のみの商品。
同一銘柄で別ページ(200g/1kg/業務用)がある場合は最小重量の商品を代表にする。
価格・在庫は商品ページのJSON-LD(ProductGroup/Product の offers)から取得する。
robots.txt は 404(制限なし)。ページ構造は商品ごとに焙煎度の選択肢(浅煎り/中深煎り)があるものがあり、
その場合 roast_level は None にする。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "辻本珈琲",
    "url": "https://tsujimoto-coffee.com/",
    "platform": "フューチャーショップ(独自ドメイン)",
    "address": "大阪府和泉市春木町1156-1",
    "prefecture": "大阪府",
    "robots_txt_status": "制限なし(2026-10-20確認。/robots.txt は404)",
    "source_note": "公式オンラインショップ(https://tsujimoto-coffee.com/c/all/beans)の各商品ページを2026-10-20に確認。"
                   "実店舗・店内焙煎は https://tsujimoto-coffee.com/brand/real-shop/ で確認。"
                   "楽天市場店(https://www.rakuten.co.jp/tsujimoto/)にも出店しているが品目の多い公式ショップを採用",
    "last_verified_at": "2026-10-20",
}

BASE = "https://tsujimoto-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5

# (商品パス, 表示名, 原産国(Noneはブレンド), 焙煎度(Noneは選択式/不明), 重量g, デカフェ除去方法, 品種)
G = "/c/all/beans/"
ITEMS = [
    (G + "src-crqg", "コスタリカ ロスアンへレス ケブラダ・グランデ農園 レポサード イエローハニー", "コスタリカ", "浅煎り", None, None, "SL-28"),
    (G + "src-esba-200g", "エチオピア シダモ ベンサ アルベゴナ CWS ナチュラル", "エチオピア", None, None, None, "エチオピア原種"),
    (G + "src-etb-200g", "エチオピア ウェスト アルシ ブルガ CWS ウォッシュド", "エチオピア", None, None, None, "エチオピア原種"),
    (G + "b_grandcru/gcrc-pst-coe", "【グランクリュ】ペルー サンタ テレサ農園 ゲイシャ ナチュラル", "ペルー", "浅煎り", None, None, "ゲイシャ"),
    (G + "single_beans/single_rwanda/src-rgn-200g", "ルワンダ ガコ農園 ブルボン ナチュラル", "ルワンダ", "浅煎り", None, None, "ブルボン"),
    (G + "src-mhmn", "メキシコ ウエウエテパン農園 ムンドマーヤ ナチュラル", "メキシコ", "浅煎り", None, None, None),
    (G + "b_grandcru/gcrc-bfvc-coe", "【グランクリュ】ブラジル ファゼンダ・ヴァレ・ド・クリスタル カトゥカイ・アス ナチュラル", "ブラジル", "浅煎り", None, None, "カトゥカイ・アス"),
    (G + "b_grandcru/gcrc-mxfh", "【グランクリュ】メキシコ ウエウエテパン農園 ゲイシャ ナチュラル", "メキシコ", "浅煎り", None, None, "ゲイシャ"),
    (G + "b_grandcru/gcrc-glgm-coe", "【グランクリュ】グァテマラ ラ・グラン マンサナ ゲイシャ エキゾチック ウォッシュド", "グアテマラ", None, None, None, "ゲイシャ"),
    (G + "src-gcz", "グァテマラ クレイジーコーヒー プラン・デ・ラ・ベガ農園 ナチュラル", "グアテマラ", "中煎り", None, None, "カトゥーラ、ブルボン"),
    (G + "b_grandcru/gcrc-qima-ces", "【グランクリュ】コロンビア エル・シレンシオ オンブリゴン イーストファーメンテーション・ウォッシュド", "コロンビア", "浅煎り", None, None, "オンブリゴン"),
    (G + "src-gap-200g", "グァテマラ アンティグア エル・ポトレロ農園 フーリーウォッシュド", "グアテマラ", "中深煎り", None, None, "カトゥーラ、カティモール"),
    (G + "src-rmw-200g", "ルワンダ マチアゾ ブルボン ウォッシュド", "ルワンダ", "浅煎り", None, None, "ブルボン"),
    (G + "src-mxndf-200g", "メキシコ ナランハ農園 ガルニカ ダブルファーメンテッド ウォッシュド", "メキシコ", "中煎り", None, None, "ガルニカ"),
    (G + "b_grandcru/gcrc-ppdl-coe", "【グランクリュ】ペルー ペーニャ・デ・レオン農園 ゲイシャ ウォッシュド", "ペルー", "浅煎り", None, None, "ゲイシャ"),
    (G + "src-crecy", "コスタリカ エル・セドロ農園 サン・イシドロ・ラブラドール イエローハニー", "コスタリカ", "浅煎り", None, None, "ティピカ"),
    (G + "b_grandcru/gcrc-hoshg", "【グランクリュ】ホンジュラス オスマンサス農園 ゲイシャ シークレットハニー", "ホンジュラス", "浅煎り", None, None, "ゲイシャ"),
    (G + "src-ban-200g", "ブラジル セーハダストレスバハス農園 イエローブルボン ナチュラル", "ブラジル", "浅煎り", None, None, "イエローブルボン"),
    (G + "src-cstg-200g", "コロンビア カーニャドゥルセ農園 ティピカ ウォッシュド", "コロンビア", "中深煎り", None, None, "ティピカ"),
    (G + "src-cpcn-200g", "コスタリカ ラ・パストーラ農園 ゴールデン・ハニー", "コスタリカ", None, None, None, "カトゥーラ、カトゥアイ"),
    (G + "src-igb-200g", "インドネシア グラン・ブルー", "インドネシア", "中深煎り", None, None, None),
    (G + "src-kkfaa200g", "ケニア ガタイシ コーヒーファクトリー ウォッシュド", "ケニア", "中煎り", None, None, "ルイル11、SL28、SL34、バティアン"),
    (G + "src-bm-no1-100g", "ブルーマウンテンNO.1 クライスデール", "ジャマイカ", "浅煎り", None, None, None),
    (G + "src-wc250", "イエメン ホワイトキャメル", "イエメン", "浅煎り", None, None, None),
    (G + "src-mygsl34-200g", "ミャンマー グリーンランド農園 ウォッシュド", "ミャンマー", "中煎り", None, None, "SL34"),
    # デカフェ
    (G + "src-decaf-dbf-200g", "デカフェ ブラジル スル・デ・ミナス ナチュラル マウンテンウォータープロセス", "ブラジル", "中深煎り", None, "マウンテンウォータープロセス", None),
    (G + "rc-decaf200", "デカフェ コロンビア -aiu- マウンテンウォータープロセス", "コロンビア", "中深煎り", None, "マウンテンウォータープロセス", None),
    (G + "rc-decaf-hb200", "デカフェ ハウスブレンド", None, None, None, None, None),
    (G + "rc-decaf-cm200", "デカフェ モカ マウンテンウォータープロセス", "エチオピア", "中煎り", None, "マウンテンウォータープロセス", None),
    (G + "rc-decaf-cbs200", "デカフェ バリアラビカ -アロナ- スイスウォータープロセス", "インドネシア", "中深煎り", None, "スイスウォータープロセス", None),
    (G + "src-decaf-rh200g", "デカフェ ホンジュラス ウォッシュド スイスウォータープロセス", "ホンジュラス", "中深煎り", None, "スイスウォータープロセス", None),
    (G + "src_decaf-mx200", "デカフェ メキシコ エル・トリウンフォ 有機", "メキシコ", "中煎り", None, None, None),
    # ブレンド・レギュラー
    (G + "b_business/src-es-sieste-500g", "スペシャルエスプレッソブレンド -シエスタ-", None, None, None, None, None),
    (G + "src-sc-espressoblend-500g", "オリジナルエスプレッソブレンド", None, "中深煎り", None, None, None),
    (G + "rc-itsumo500", "イツモブレンド", None, "中煎り", None, None, None),
    (G + "rc-itsumoice500", "イツモアイスブレンド", None, "中煎り", None, None, None),
    (G + "rc-www-200g", "WINTER winter WINTER ブレンド(冬季限定)", None, None, None, None, None),
    (G + "rc-sbfp250", "そよ風ブレンド(季節限定)", None, "浅煎り", None, None, None),
    (G + "rc-ab250", "ほろにがブレンド", None, "中深煎り", None, None, None),
    (G + "701624", "キリマンジャロ タンザニア AA", "タンザニア", "中煎り", None, None, None),
    (G + "717212", "スマトラ マンデリン", "インドネシア", "深煎り", None, None, None),
    (G + "633279", "カリビアンブレンド(プレミアムアイスブレンド)", None, None, None, None, None),
    (G + "610706", "ブルーマウンテンブレンド", None, "中煎り", None, None, None),
    (G + "607655", "お茶屋が考えるまろやかブレンド", None, None, None, None, None),
    (G + "rc-brno2-500g", "ブラジルNo.2 サントス ナチュラル", "ブラジル", "浅煎り", None, None, None),
]

# 商品ページの説明文が別商品(デカフェ コロンビア)のものになっているため、味の説明は採用しない
NO_FLAVOR = {G + "src-cstg-200g"}

LD_PATTERN = re.compile(r'application/ld\+json[^>]*>(.*?)</script>', re.DOTALL)
VARIANT_WEIGHT = re.compile(r"-(\d+)g")
NAME_WEIGHT = re.compile(r"(\d+)\s*g")


def fetch(url: str):
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    if resp.status_code != 200:
        print(f"[warn] 取得失敗: {url} (HTTP {resp.status_code})")
        return None
    resp.encoding = "utf-8"
    return resp.text


def product_ld(page: str) -> dict | None:
    for block in LD_PATTERN.findall(page):
        try:
            d = json.loads(block, strict=False)
        except json.JSONDecodeError:
            continue
        if d.get("@type") in ("Product", "ProductGroup"):
            return d
    return None


def min_weight_offer(d: dict) -> tuple[int | None, int | None, bool]:
    """(価格, 重量g, 在庫あり)。最小重量のバリエーション(複数なら在庫ありを優先)。"""
    name = html.unescape(d.get("name", "")).replace("<br>", " ").replace("<br />", " ")
    if d.get("@type") == "ProductGroup":
        rows = []
        for v in d.get("hasVariant") or []:
            m = VARIANT_WEIGHT.search(v.get("@id", ""))
            w = int(m.group(1)) if m else None
            off = v.get("offers") or {}
            rows.append((w, int(off["price"]), off.get("availability", "").endswith("InStock")))
        if not rows:
            return None, None, False
        weights = [r[0] for r in rows if r[0] is not None]
        if weights:
            w0 = min(weights)
            same = [r for r in rows if r[0] == w0]
        else:
            m = NAME_WEIGHT.search(name)
            w0 = int(m.group(1)) if m else None
            same = rows
        instock = [r for r in same if r[2]]
        pick = (instock or same)[0]
        return pick[1], w0, bool(instock)
    off = d.get("offers") or {}
    m = NAME_WEIGHT.search(name)
    price = int(off["price"]) if off.get("price") else None
    return price, int(m.group(1)) if m else None, str(off.get("availability", "")).endswith("InStock")


def flavor_from_description(d: dict) -> str | None:
    desc = html.unescape(d.get("description", ""))
    desc = re.sub(r"<br\s*/?>|</p>|</div>|</h3>", "\n", desc)
    desc = re.sub(r"<[^>]+>", "", desc)
    lines = [ln.strip() for ln in desc.split("\n") if ln.strip()]
    good = [ln for ln in lines if "。" in ln and "：" not in ln[:12]
            and not any(k in ln for k in ("ヒーロースター", "お届け", "焙煎機", "業務用", "グラインダー", "クーポン"))]
    if not good:
        return None
    text = " ".join(good[:2])
    text = re.sub(r"^.{0,40}?\d+g\s+", "", text)  # 先頭の商品名(「…… 200g 」)を除く
    return text[:200]


def build_record(path, name, origin, roast, _w, decaf_process, variety) -> dict | None:
    url = BASE + path
    page = fetch(url)
    if not page:
        return None
    d = product_ld(page)
    if not d:
        print(f"[warn] JSON-LDなし: {url}")
        return None
    price, weight, in_stock = min_weight_offer(d)
    if price is None:
        print(f"[warn] 価格取得失敗: {url}")
        return None
    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "shop_attribute"
    stock_status = "販売中" if in_stock else "完売"
    processing = parsed["processing_method"]
    if decaf_process and processing and ("ウォータープロセス" in processing):
        # デカフェ除去方法は decaf_process に持たせ、精製方法(ナチュラル等)とは混ぜない
        processing = None
        for kw in ("ナチュラル", "ウォッシュド"):
            if kw in name:
                processing = kw
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "variety": variety,
        "decaf_process": decaf_process,
        "flavor_notes": None if path in NO_FLAVOR else flavor_from_description(d),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        rec = build_record(*item)
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_tsujimotocoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tsujimotocoffee.json に出力しました")


if __name__ == "__main__":
    main()
