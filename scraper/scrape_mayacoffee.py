# -*- coding: utf-8 -*-
"""
scrape_mayacoffee.py

マヤ珈琲焙煎所(https://mayacoffee.theshop.jp/、東京都北区東十条5-2-9 豊田ビル1F)の商品情報を取得する。BASE(theshop.jp)。

【店舗発見の経緯】
全国再調査(東京都東部・北部)の新規発掘で発見。

【確認内容(2026-10-21)】
BASE https://mayacoffee.theshop.jp/ の商品ページ(sitemap.xml)を2026-10-21に確認。豆の品目はBASE(26点)が自社カート https://www.mayacoffee.jp/coffee-beans/ (3点のみ)より揃うためBASEを採用。公式 https://www.mayacoffee.jp/top/aboutus/ に「豆森株式会社が運営する自家焙煎コーヒー専門店」「Kaleido電気直火式焙煎機でご注文ごとに生豆を焙煎するオーダー焙煎」、/top/access/ に本店所在地(北区東十条5丁目2番9号豊田ビル1F)。BASEの23銘柄は価格・重量が「生豆100g時の税込価格」(焙煎後は水分が抜け1〜2割減、焙煎度は購入時に選択。weight_gは生豆100g、roastは商品ページの推奨焙煎)。別に焙煎豆200g表記の3銘柄(熔岩・嵐空・破暁、2330円)を200gで採用。ドリップバッグ/パック・水出しパック・羊羹・器具・海外発送料は除外。

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
    "name": "マヤ珈琲焙煎所",
    "url": "https://mayacoffee.theshop.jp/",
    "platform": "BASE(theshop.jp)",
    "address": "東京都北区東十条5-2-9 豊田ビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(BASE系の標準的な記述。python-requests/curl等のみ個別にDisallowで、識別可能なUser-Agentを使用。間隔5秒以上)",
    "source_note": "BASE https://mayacoffee.theshop.jp/ の商品ページ(sitemap.xml)を2026-10-21に確認。豆の品目はBASE(26点)が自社カート https://www.mayacoffee.jp/coffee-beans/ (3点のみ)より揃うためBASEを採用。公式 https://www.mayacoffee.jp/top/aboutus/ に「豆森株式会社が運営する自家焙煎コーヒー専門店」「Kaleido電気直火式焙煎機でご注文ごとに生豆を焙煎するオーダー焙煎」、/top/access/ に本店所在地(北区東十条5丁目2番9号豊田ビル1F)。BASEの23銘柄は価格・重量が「生豆100g時の税込価格」(焙煎後は水分が抜け1〜2割減、焙煎度は購入時に選択。weight_gは生豆100g、roastは商品ページの推奨焙煎)。別に焙煎豆200g表記の3銘柄(熔岩・嵐空・破暁、2330円)を200gで採用。ドリップバッグ/パック・水出しパック・羊羹・器具・海外発送料は除外。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://mayacoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(商品ページに明記があるものだけ), 産地(ブレンドはNone))
ITEMS = [('150687519', '破暁 DAY BREAK - TANZANIA', 200, None, None, 'タンザニア'),
 ('150683417', '熔岩 MAGMA - GUATEMALA', 200, None, None, 'グアテマラ'),
 ('150685984', '嵐空 STORMY SKY - RWANDA', 200, None, None, 'ルワンダ'),
 ('87509815', 'MAYAオリジナルブレンド', 100, 'ブレンド', '中煎り', None),
 ('87412856', 'パプアニューギニア ハイランドスウィート キガバー農園', 100, None, '中深煎り', 'パプアニューギニア'),
 ('87531719', 'モカマイルドブレンド', 100, 'ブレンド', '中煎り', None),
 ('87548315', 'ベーシックブレンド', 100, 'ブレンド', '中煎り', None),
 ('87412926', 'インドネシア マンデリン ビンタンリマ', 100, None, '中深煎り', 'インドネシア'),
 ('87412816', 'ルワンダ スカイヒル コプロカWS', 100, None, '浅煎り', 'ルワンダ'),
 ('86920869', 'ペルー アルパカ JASオーガニック', 100, None, '中浅煎り', 'ペルー'),
 ('87376624', 'タンザニア キゴマ キボーAA ディープブルー', 100, None, '中煎り', 'タンザニア'),
 ('83539666', 'エチオピア イルガチャフィー ベレカ G1(ウォッシュト)', 100, None, '中浅煎り', 'エチオピア'),
 ('87376577', 'ミャンマー ゴールデンロック（レッドハニー）', 100, None, '中浅煎り', 'ミャンマー'),
 ('87376486', '中国 雲南 天空農園 プーアル(washed)', 100, None, '中煎り', '中国'),
 ('87376384', 'イエメン バニーマタル', 100, None, '中浅煎り', 'イエメン'),
 ('87412769', 'ケニア マサイ AA', 100, None, '中深煎り', 'ケニア'),
 ('87413004', 'ジャマイカ ブルーマウンテン No.1', 100, None, '中浅煎り', 'ジャマイカ'),
 ('87376336', 'パナマ ベルリナ農園 ナランハル ゲイシャ', 100, None, '中浅煎り', 'パナマ'),
 ('87376106', 'グアテマラ カフェインレス マンテンウォータープロセス', 100, None, '中煎り', 'グアテマラ'),
 ('86921272', 'ニカラグア サンタアナ農園 SHG', 100, None, '中浅煎り', 'ニカラグア'),
 ('86921160', 'エルサルバドル サンタ・エレナ農園 ブルボン', 100, None, '中浅煎り', 'エルサルバドル'),
 ('86921049', 'グアテマラ ゴールデンパレンシア リオ コロラド農園SHB', 100, None, '中煎り', 'グアテマラ'),
 ('86920951', 'コスタリカ セントタラス SHB ガンボア農園', 100, None, '中浅煎り', 'コスタリカ'),
 ('86882597', 'ブラジル サントアントニオ プレミアムショコラ ナチュラル', 100, None, '中煎り', 'ブラジル'),
 ('86882492', 'コロンビア スウィートベリー SUP', 100, None, '中煎り', 'コロンビア'),
 ('87376655', 'ブルンジ カジャブレWS ブルボン', 100, None, '中煎り', 'ブルンジ')]

# 豆以外(ドリップバッグ・セット・ギフト・定期便・器具・雑貨・インフューズド等)や大容量のみの商品など、収録しないsitemap上の商品ID
EXCLUDED_IDS = {'92696645', '87531361', '87519975', '87520652', '146474533', '88756711', '87520739', '148532709', '87531110', '87529428', '92696644'}

# 説明文の整形: 開始マーカー(あれば以降を使う)、この文字列以降は切る、この文字列で始まる行は捨てる
DESC_START_MARKER = None
DESC_CUT_MARKERS = ['※生豆焙煎後']
DESC_DROP_LINE_PREFIXES = ['推奨焙煎', '※生豆100g時', '※生豆焙煎後']

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
    with open("data_mayacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mayacoffee.json に出力しました")


if __name__ == "__main__":
    main()
