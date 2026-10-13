# -*- coding: utf-8 -*-
"""
scrape_kagurakoffee.py

神楽珈琲(https://morinouendry.thebase.in/、愛媛県喜多郡内子町川中181)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(愛媛県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): サイトマップ69商品のうち、焙煎豆100g 63銘柄を収録(100g固定、全商品商品名に100g表記)。除外: 【リキュールインフューズド】2件・【インフューズド】2件(香り付け製法)、【数量限定セット】100gx3の2件(セット)。「在庫の一部バリエーションのみ購入可(partially_purchasable)」は販売中として扱う。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが容量表記・キャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "神楽珈琲",
    "url": "https://morinouendry.thebase.in/",
    "platform": "BASE",
    "address": "愛媛県喜多郡内子町川中181",
    "prefecture": "愛媛県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://morinouendry.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('161357786', '【インドネシア】 ガヨマウンテン エキストリームウォッシュド', 100, None, None),
    ('161356610', '【ブラジル】オウトプレト ウォッシュド イパネマ農園', 100, None, None),
    ('161347893', '【ニカラグア】 ジャバニカ ウォッシュド ロスアルティプラノス農園', 100, None, None),
    ('161346973', '【ニカラグア】 パカマラ ウォッシュド ロスアルティプラノス農園', 100, None, None),
    ('160964033', '【ルワンダ】ベストオブルワンダ2025 #3 TUK生産者組合', 100, None, None),
    ('146589866', '【コロンビア】 トリマ エルビノ ウォッシュド カフェグランデ農協', 100, None, None),
    ('160046772', '【ペルー】 アルト・パロマール ウォッシュド', 100, None, None),
    ('91183589', '【エチオピア】 グジ アナソラ アナエロビックナチュラル', 100, None, None),
    ('43730467', '【グアテマラ】オリエンテ ナチュラル', 100, None, None),
    ('153919513', '【タイ】スペシャルウォッシュド プパンナ農園', 100, None, None),
    ('146588609', '【エチオピア】 グジ シャキッソ ゴールデンハニー', 100, None, None),
    ('58176357', '【イエメン】モカハラズ ワディセイル ナチュラル', 100, None, None),
    ('112029727', '【インドネシア】 マジャラヤ カーボニックマセレーションナチュラル ロア農園', 100, None, None),
    ('87589127', '【インドネシア】 マンデリン スマトラタイガー S19+', 100, None, None),
    ('54214459', '【エチオピア】イルガチェフェ ゲルシ ナチュラル', 100, None, None),
    ('118431688', '【エチオピア】 カップオブエクセレンス#27 タデッセ農園', 100, None, None),
    ('87793524', '【エチオピア】 タミル・タデッセ チャラカ アナエロビックハニー', 100, None, None),
    ('91156563', '【エチオピア】 ニグセ・ゲメダ カラモ アナエロビック', 100, None, None),
    ('145967068', '【エチオピア】 エチオピア ベレテ・ゲラ オバトリ', 100, None, None),
    ('131117272', '【エチオピア】 エチオピア ベレテ・ゲラ ユクロ', 100, None, None),
    ('97302618', '【エチオピア】 ベンチマジ ゴリゲシャ スロードライ ナチュラル', 100, None, None),
    ('131373515', '【グアテマラ】 パカマラ ウォッシュド エルインヘルト農園', 100, None, None),
    ('91249398', '【ケニア】カムワンギ AA ウォッシュド ンガリアマ生産者組合', 100, None, None),
    ('108672821', '【ケニア】 サンルージュAA フリーウォッシュド', 100, None, None),
    ('71676551', '【コスタリカ】カップオブエクセレンス#15 ドン・ホエル農園', 100, None, None),
    ('83015432', '【コスタリカ】 コフィアディベルサ農園 ラウリナ オーバル ハニー', 100, None, None),
    ('131387269', '【コスタリカ】 ビジャサルチ ブラックチェリーナチュラル モンテジャノボニート農園', 100, None, None),
    ('146162087', '【コロンビア】ウシュウシュ アンチマセレーション エル・パライソ農園', 100, None, None),
    ('146167925', '【コロンビア】 ナリーニョ スプレモ フローラルミスト', 100, None, None),
    ('146242055', '【コロンビア】 ピンクブルボン ハニー インマクラーダ農園', 100, None, None),
    ('146239808', '【コロンビア】 ミカヴァ タビ ハイブリッドウォッシュド マルセラ農園', 100, None, None),
    ('146497082', '【コスタリカ】 ミビリジ ナチュラル ロストーニョ農園', 100, None, None),
    ('146501816', '【コスタリカ】 ムンドノーボ カーボニックマセレーションナチュラル ロストーニョ農園', 100, None, None),
    ('138229425', '【コロンビア】 リサラルダ カルチャリングウォッシュド ラ・リビエラ農園', 100, None, None),
    ('131389301', '【コロンビア】 レッドブルボン ゴールドウォッシュ サントゥアリオ農園', 100, None, None),
    ('131136019', '【タンザニア】 ンゴロンゴロ パカマラ アカシアヒルズ農園', 100, None, None),
    ('146503008', '【デカフェ】 メキシコ チアパス ウォッシュド', 100, None, None),
    ('57927169', '【ジャマイカ】ブルーマウンテンNO.1 ブルーバロン', 100, None, None),
    ('131371837', '【ドミニカ】 プリンセサ ワイニーナチュラル アルフレドディアス農園', 100, None, None),
    ('146424929', '【ニカラグア】 イエローパカマラ ウォッシュド サンホセ農園', 100, None, None),
    ('146408638', '【ニカラグア】 エチオサル ウォッシュド ラ・ウェラ農園', 100, None, None),
    ('146407115', '【ニカラグア】 パカマラ ウォッシュド サンタマリア農園', 100, None, None),
    ('132124827', '【ニカラグア】 マラカトゥーラ ナチュラル エル・ナランホ農園', 100, None, None),
    ('132123449', '【ニカラグア】 マラカトゥーラ フリーウォッシュド エル・ナランホ農園', 100, None, None),
    ('91295628', '【パナマ】 カトゥアイ モストマセレーション アブ農園', 100, None, None),
    ('87792138', '【パナマ】 パカマラ ナチュラル ヴィクトリウス農園', 100, None, None),
    ('87792242', '【パナマ】 レッドブルボン アナエロビックナチュラル バンビート農園', 100, None, None),
    ('132122649', '【ブラジル】 アララ ナチュラル セーハダストレスバハス農園', 100, None, None),
    ('131347896', '【ブラジル】 アララ ハニー カッシャンブー農園', 100, None, None),
    ('146494853', '【ブラジル】 イカツ ナチュラル パッセイオ農園', 100, None, None),
    ('118438758', '【ブラジル】 カップオブエクセレンス#8 ビオマカフェ農園', 100, None, None),
    ('46152140', '【ブラジル】フルッタメルカドン ドナネネン農園', 100, None, None),
    ('146152030', '【ベネズエラ】 カツーラ フリーウォッシュド ムクカイ農園', 100, None, None),
    ('133761544', '【ペルー】 エスペランサ＆ロメリージョ', 100, None, None),
    ('133764603', '【ペルー】 ティピカ アナエロビックウォッシュド ミラフローレス農園', 100, None, None),
    ('87589306', '【ペルー】 ブルーコンドル', 100, None, None),
    ('131124285', '【ペルー】 レッドブルボン エクスペリメンタルウォッシュ トゥンキマユ農園', 100, None, None),
    ('146426469', '【ホンジュラス】 IH90 ラス・ウバス農園', 100, None, None),
    ('91294853', '【ホンジュラス】 カトゥアイ ナチュラル エル・プエンテ農園', 100, None, None),
    ('91295112', '【ホンジュラス】 ジャバ ナチュラル モゴラ農園', 100, None, None),
    ('131128533', '【東ティモール】 ダウルフシュ ウォッシュド', 100, None, None),
    ('131125716', '【中国】 雲南省 春醸醉', 100, None, None),
    ('83016524', '【エチオピア】 モカシダモ テフェリケラ ウォッシュド', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'153919513': 'タイ', '131125716': '中国', '131128533': '東ティモール'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
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
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,  # 商品名の「ハイブリッド」等がハイロースト誤検出されるため、明示値のみ採用
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


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kagurakoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kagurakoffee.json に出力しました")


if __name__ == "__main__":
    main()
