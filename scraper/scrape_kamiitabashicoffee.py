# -*- coding: utf-8 -*-
"""
scrape_kamiitabashicoffee.py

上板橋珈琲焙煎所(https://tostand.buyshop.jp/、東京都板橋区上板橋3-4-11 二村ビル1F)の商品情報を取得する。BASE(buyshop.jp)。

【店舗発見の経緯】
全国再調査(東京都東部・北部)の新規発掘で発見。

【確認内容(2026-10-21)】
BASE https://tostand.buyshop.jp/ の商品ページ(sitemap.xml)・/about(「オーダーを頂いてから英国式焙煎機を使用しオーダー毎に生豆を焙煎」)を2026-10-21に確認。店舗は公式 https://jikabaisen-kissa.com/schedule/ の営業日＆アクセス(板橋区上板橋3丁目4-11 二村ビル1F、上板橋駅北口徒歩3分)。重量は生豆表記(商品ページ「100g(生豆時質量)※焙煎度により質量は90%〜80%程度」)で、焙煎後は80〜90%。インフューズド＆ハニー3種、ウィスキー/ラム/シェリー熟成豆(酒に漬ける加工)5種、水出しパック、ドリップバッグ・定期便は除外。豆リストページの日付は2025-10-01の表示あり。

【対象商品について】
商品名・重量・焙煎度・産地は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明文は商品ページから実行時に取得する。
ITEMSにもEXCLUDED_IDSにも無い商品がsitemap.xmlに現れた場合は、新商品の可能性があるため
警告を表示する(自動では収録しない)。

【robots.txtについて】
BASE系の標準的な記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "上板橋珈琲焙煎所",
    "url": "https://tostand.buyshop.jp/",
    "platform": "BASE(buyshop.jp)",
    "address": "東京都板橋区上板橋3-4-11 二村ビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(BASE系の標準的な記述。python-requests/curl等のみ個別にDisallowで、識別可能なUser-Agentを使用。間隔5秒以上)",
    "source_note": "BASE https://tostand.buyshop.jp/ の商品ページ(sitemap.xml)・/about(「オーダーを頂いてから英国式焙煎機を使用しオーダー毎に生豆を焙煎」)を2026-10-21に確認。店舗は公式 https://jikabaisen-kissa.com/schedule/ の営業日＆アクセス(板橋区上板橋3丁目4-11 二村ビル1F、上板橋駅北口徒歩3分)。重量は生豆表記(商品ページ「100g(生豆時質量)※焙煎度により質量は90%〜80%程度」)で、焙煎後は80〜90%。インフューズド＆ハニー3種、ウィスキー/ラム/シェリー熟成豆(酒に漬ける加工)5種、水出しパック、ドリップバッグ・定期便は除外。豆リストページの日付は2025-10-01の表示あり。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://tostand.buyshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(商品ページに明記があるものだけ), 産地(ブレンドはNone))
ITEMS = [('159897344', '中国 雲南 サルチモール ジュンマバレー農園', 100, None, '中煎り', '中国'),
 ('97517772', '中国 雲南 琥珀杏仁（コハクアンニン）', 100, None, '深煎り', '中国'),
 ('104550674', 'インドネシア ミトラG1', 100, None, '深煎り', 'インドネシア'),
 ('145932327', 'ブラジル ドーナス ド カフェ パルプドナチュラル', 100, None, '深煎り', 'ブラジル'),
 ('154549931', 'タンザニア イドゥンダAB ナチュラル', 100, None, '深煎り', 'タンザニア'),
 ('153127813', 'エチオピア ゲイシャジャスミン', 100, None, '浅煎り', 'エチオピア'),
 ('153127683', 'コロンビア ゲイシャ サンビクトリノ農園', 100, None, '浅煎り', 'コロンビア'),
 ('150441033', 'インドネシア マンデリン バタックブルー', 100, None, '中深煎り', 'インドネシア'),
 ('150440871', 'ブラジル マリア セレステ', 100, None, '中深煎り', 'ブラジル'),
 ('150441367', 'コロンビア ベンジャビスタ農園', 100, None, '中深煎り', 'コロンビア'),
 ('149809657', '【カフェインレス】ホンジュラス ウォータープロセス', 100, None, '深煎り', 'ホンジュラス'),
 ('147189951', 'コロンビア ガレラス', 100, None, '深煎り', 'コロンビア'),
 ('145931693', 'イエメン モカ ファーマーズギフト', 100, None, '中煎り', 'イエメン'),
 ('145276141', 'ブルンジ カジャブーレWS', 100, None, '中深煎り', 'ブルンジ'),
 ('71674081', 'エチオピア グジ シャキッソ ゴールデンハニー', 100, None, '中煎り', 'エチオピア'),
 ('147945926', 'エチオピア シティロースト ゲデオ SPナチュラル', 100, None, '中深煎り', 'エチオピア'),
 ('144029846', 'コロンビア エルパライソ ライチ ダブルアナエロビックF', 100, None, '浅煎り', 'コロンビア'),
 ('142440197', 'インドネシア ナチュラル アチェ タケンゴン', 100, None, '浅煎り', 'インドネシア'),
 ('142439325', 'ブラジル ゲイシャ グアリロバ農園 ナチュラル アナエロビック', 100, None, '浅煎り', 'ブラジル'),
 ('138415562', 'コスタリカ ドン・カイート農園 ホワイトハニー', 100, None, '深煎り', 'コスタリカ'),
 ('138404524', 'エチオピア シティロースト ゲルチャキンドゥ ウォッシュド', 100, None, '中深煎り', 'エチオピア'),
 ('138415071', '【カフェインレス】メキシコ ハイロースト 有機JAS 認証生豆100%使用', 100, None, '中煎り', 'メキシコ'),
 ('135120611', 'インドネシア ハイロースト マンデリン ビンタンリマ', 100, None, '中煎り', 'インドネシア'),
 ('135121127', 'ブラジル ピーベリー ポソス・デ・カルダス', 100, None, '中深煎り', 'ブラジル'),
 ('127000362', 'ブラジル ボンジャルディン農園 パルプドナチュラル', 100, None, '中深煎り', 'ブラジル'),
 ('104549828', 'グァテマラ エルボスケ', 100, None, '深煎り', 'グアテマラ'),
 ('123431679', 'エチオピア ゲルチャキンドゥ スーパーナチュラル', 100, None, '中煎り', 'エチオピア'),
 ('123431465', 'エチオピア ゲルチャキンドゥ ウォッシュド', 100, None, '浅煎り', 'エチオピア'),
 ('60325931', 'インドネシア マンデリン ビンタンリマ', 100, None, '深煎り', 'インドネシア'),
 ('116362816', 'ペルー サンビセンテ', 100, None, '深煎り', 'ペルー'),
 ('60325119', 'ルワンダ ウォッシュド スカイヒル コプロカ', 100, None, '中深煎り', 'ルワンダ'),
 ('100419719', 'エチオピア イルガチェフェ コンガ農協 ナチュラル', 100, None, '中煎り', 'エチオピア'),
 ('104547487', 'エチオピア イルガチェフェ ガルガリグディティ', 100, None, '深煎り', 'エチオピア'),
 ('94853130', '【カフェインレス】グァテマラ ウォータープロセス', 100, None, '深煎り', 'グアテマラ'),
 ('69450726', 'エルサルバドル サンタ・エレナ農園', 100, None, '中深煎り', 'エルサルバドル'),
 ('61470849', 'ブラジル サントアントニオ プレミアムショコラ', 100, None, '深煎り', 'ブラジル'),
 ('69448812', '【カフェインレス】メキシコ チアパス 有機JAS 認証生豆100%使用', 100, None, '中深煎り', 'メキシコ'),
 ('69454885', 'エチオピア イルガチェフェ ブナブナ', 100, None, '浅煎り', 'エチオピア'),
 ('69449766', 'タンザニア サウステラ', 100, None, '中深煎り', 'タンザニア'),
 ('94439551', 'エチオピア ゲデオ スーパーナチュラル', 100, None, '浅煎り', 'エチオピア'),
 ('74079544', 'グァテマラ ファンシーサンタロッサ', 100, None, '中深煎り', 'グアテマラ'),
 ('60326400', 'エチオピア イルガチェフェ ベレカ G１', 100, None, '中煎り', 'エチオピア')]

# 豆以外(ドリップバッグ・セット・ギフト・定期便・器具・雑貨・インフューズド等)や大容量のみの商品など、収録しないsitemap上の商品ID
EXCLUDED_IDS = {'144595566', '74077293', '147923062', '148052627', '145932075', '156707093', '76843357', '83917559', '105412939', '107618497', '159897172', '124847943'}

# 説明文の整形: 開始マーカー(あれば以降を使う)、この文字列以降は切る、この文字列で始まる行は捨てる
DESC_START_MARKER = '特徴：'
DESC_CUT_MARKERS = ['◾']
DESC_DROP_LINE_PREFIXES = []

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one('[class*="item-detail_description"]')
    if el:
        text = el.get_text("\n")
    else:
        og = soup.select_one('meta[property="og:description"]')
        text = og.get("content", "") if og else ""
    text = html.unescape(text)
    if DESC_START_MARKER and DESC_START_MARKER in text:
        text = text.split(DESC_START_MARKER, 1)[1]
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not any(ln.startswith(p) for p in DESC_DROP_LINE_PREFIXES)]
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    cut = len(text)
    for marker in DESC_CUT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            cut = min(cut, idx)
    return text[:cut].strip()[:400] or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None,
                 roast_level: str | None, origin: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    desc = clean_description(soup)
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "product_description"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def check_new_items() -> None:
    """sitemap.xmlに未分類の商品があれば警告する(収録はしない)。"""
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] sitemap取得失敗 ({e})")
        return
    known = {item[0] for item in ITEMS} | set(EXCLUDED_IDS)
    for item_id in dict.fromkeys(re.findall(r"/items/(\d+)", resp.text)):
        if item_id not in known:
            print(f"[warn] 未分類の商品がsitemapにあります: {BASE_URL}/items/{item_id}")
    time.sleep(REQUEST_INTERVAL)


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        finally:
            time.sleep(REQUEST_INTERVAL)
        if record is not None:
            records.append(record)
    return records


def main():
    check_new_items()
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kamiitabashicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kamiitabashicoffee.json に出力しました")


if __name__ == "__main__":
    main()
