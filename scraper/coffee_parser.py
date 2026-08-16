# -*- coding: utf-8 -*-
"""
商品名パースロジック(coffee_parser.py)

これまでの調査(産地マスタ・特定銘柄・精選方法・グレード・焙煎度)を元にした
キーワードマッチングパーサー。parser_test.pyで検証したロジックをスクレイパーから
再利用できるようモジュール化したもの。
"""

import json
import os
import re

# --- 産地マスタ: 国名キーワード(日本語) -------------------------------------
ORIGIN_COUNTRY_KEYWORDS = {
    "ベトナム": "ベトナム",
    "タイ": "タイ",
    "グァテマラ": "グアテマラ",
    "グアテマラ": "グアテマラ",
    "ガテマラ": "グアテマラ",
    "ドミニカ": "ドミニカ共和国",
    "エチオピア": "エチオピア",
    "ルワンダ": "ルワンダ",
    "パナマ": "パナマ",
    "ブラジル": "ブラジル",
    "コロンビア": "コロンビア",
    "パプアニューギニア": "パプアニューギニア",
    "東ティモール": "東ティモール",
    "イエメン": "イエメン",
    "メキシコ": "メキシコ",
    "インドネシア": "インドネシア",
    "ケニア": "ケニア",
    "タンザニア": "タンザニア",
    "ジャマイカ": "ジャマイカ",
    "コスタリカ": "コスタリカ",
    "ホンジュラス": "ホンジュラス",
    "ボリビア": "ボリビア",
    "ペルー": "ペルー",
    "エクアドル": "エクアドル",
    "スーダン": "スーダン",
}

# --- 産地マスタ: 国名キーワード(英語) ---------------------------------------
# 注意: "dominica"(ドミニカ国。カリブ海の小島嶼国で、"dominican republic"
# =ドミニカ共和国とは別の国)は、"dominican republic"の文字列に前方一致で
# 含まれてしまう("dominican republic".startswith("dominica"))。dictの反復は
# 挿入順で先勝ちのため、"dominica"は必ず"dominican republic"より後ろに
# 置くこと(先に置くと、本来ドミニカ共和国と判定すべき商品まで
# ドミニカ国と誤判定してしまう)。
ORIGIN_COUNTRY_KEYWORDS_EN = {
    "ethiopia": "エチオピア", "guatemala": "グアテマラ", "brazil": "ブラジル",
    "colombia": "コロンビア", "kenya": "ケニア", "tanzania": "タンザニア",
    "rwanda": "ルワンダ", "panama": "パナマ", "vietnam": "ベトナム",
    "indonesia": "インドネシア", "jamaica": "ジャマイカ", "costa rica": "コスタリカ",
    "honduras": "ホンジュラス", "yemen": "イエメン", "mexico": "メキシコ",
    "dominican republic": "ドミニカ共和国", "papua new guinea": "パプアニューギニア",
    "burundi": "ブルンジ", "el salvador": "エルサルバドル", "nicaragua": "ニカラグア",
    "bolivia": "ボリビア", "peru": "ペルー", "ecuador": "エクアドル", "sudan": "スーダン",
    "dominica": "ドミニカ国",
}

# --- 地域名マスタ(国への逆引き用) -------------------------------------------
REGION_TO_COUNTRY = {
    "セラード": "ブラジル", "モジアナ": "ブラジル", "スル・デ・ミナス": "ブラジル",
    "ウイラ": "コロンビア", "ナリーニョ": "コロンビア", "トリマ": "コロンビア",
    "アンティグア": "グアテマラ", "ウエウエテナンゴ": "グアテマラ",
    "タラス": "コスタリカ", "ウエストバレー": "コスタリカ",
    "コパン": "ホンジュラス", "マルカラ": "ホンジュラス",
    "ボケテ": "パナマ", "ブルーマウンテン": "ジャマイカ",
    "ヌエバセゴビア": "ニカラグア",
    "アパネカ": "エルサルバドル", "イラマテペック": "エルサルバドル",
    "イルガチェフェ": "エチオピア", "イルガチャフェ": "エチオピア",
    "シダモ": "エチオピア", "ジマ": "エチオピア", "ハラー": "エチオピア", "ボンガ": "エチオピア",
    "マタリ": "イエメン", "キリマンジャロ": "タンザニア",
    "ニエリ": "ケニア", "キリニャガ": "ケニア",
    "マンデリン": "インドネシア", "トラジャ": "インドネシア", "スラウェシ": "インドネシア",
    "バリ": "インドネシア", "ガヨ": "インドネシア",
    "コナ": "アメリカ(ハワイ)", "シグリ": "パプアニューギニア",
    "ハラバコア": "ドミニカ共和国",
    "Los Pirineos": "エルサルバドル",  # Finca Los Pirineos(パカマラ種の発祥農園として知られる)
}

# --- 特定銘柄マスタ(全日本コーヒー公正取引協議会 14銘柄) ----------------------
DESIGNATED_BRAND_KEYWORDS = {
    "ブルーマウンテン": ("ブルーマウンテン", "ジャマイカ", None),
    "ハイマウンテン": ("ハイマウンテン", "ジャマイカ", None),
    "クリスタルマウンテン": ("クリスタルマウンテン", "キューバ", None),
    "アンティグア": ("グアテマラアンティグア", "グアテマラ", None),
    "コロンビアスプレモ": ("コロンビアスプレモ", "コロンビア", None),
    "モカハラー": ("モカ・ハラー", "エチオピア", None),
    "モカマタリ": ("モカ・マタリ", "イエメン", None),
    "キリマンジャロ": ("キリマンジャロ", "タンザニア", "ブコバ地区産を除く"),
    "トラジャ": ("トラジャ", "インドネシア", None),
    "カロシ": ("カロシ", "インドネシア", None),
    "ガヨマウンテン": ("ガヨマウンテン", "インドネシア", None),
    "マンデリン": ("マンデリン", "インドネシア", "ガヨマウンテン地区(タケンゴン周辺)を除く"),
    "ハワイコナ": ("ハワイコナ", "アメリカ", None),
}

# --- 精選方法マスタ(日英表記ゆれの正規化) ------------------------------------
# 店舗によって精選方法の表記が日本語(「ウォッシュド」)だったり英語
# (「Washed」)だったり、綴りゆれ(wet hulled / wet-hulled / giling basah等)も
# あるため、意味が同じでも別の値として扱われてしまう問題が実データ調査で
# 判明した。正規化ルールはPython(このファイル)とフロントエンド(用語解説
# タブの英語併記表示)の両方から参照するため、`data/processing_method_synonyms.json`
# を唯一の情報源とし、英語名を別の場所にハードコードで二重管理しない。
#
# マッチ順序について: 「Anaerobic Natural(36 hours aerobic fermentation
# followed by 48 hours anaerobic fermentation)」のような複合的な精選方法の
# 説明文では、より具体的な工程名(アナエロビック等)を、出現しやすい一般的な
# 語(「natural」等)より先に判定できるよう、JSON側のキー順を「特殊な工程 →
# 一般的な工程」にしている(dictはPython 3.7+で挿入順を保持する)。
_PROCESSING_METHOD_SYNONYMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "processing_method_synonyms.json"
)
with open(_PROCESSING_METHOD_SYNONYMS_PATH, encoding="utf-8") as _f:
    _PROCESSING_METHOD_MASTER = json.load(_f)

PROCESSING_METHOD_SYNONYMS = {
    canonical: entry["synonyms"] for canonical, entry in _PROCESSING_METHOD_MASTER.items()
}


def detect_processing_method(text):
    """テキスト中から精選方法のシノニムを検出し、正規化した日本語名を返す。

    商品名のようなフリーテキストから「そこに精選方法への言及があるかどうか」を
    判定する用途(見つからなければNoneを返し、商品名全体を誤って精選方法として
    扱わないようにする)。
    """
    if not text:
        return None
    lowered = text.lower()
    for canonical, synonyms in PROCESSING_METHOD_SYNONYMS.items():
        for kw in synonyms:
            if kw.lower() in lowered:
                return canonical
    return None


def normalize_processing_method(raw_method):
    """店舗の構造化データ等から既に抽出済みの精選方法ラベルを正規化する。

    シノニム辞書に一致すれば正式名称を返し、一致しなければ(未知の表記の
    可能性があるため)情報を失わないよう元のテキストをそのまま返す。
    """
    return detect_processing_method(raw_method) or raw_method

# --- 後処理タグマスタ --------------------------------------------------------
POST_PROCESSING_KEYWORDS = {
    "バレルエイジド": "バレルエイジド(樽熟成)",
    "樽熟成": "バレルエイジド(樽熟成)",
    "barrel aged": "バレルエイジド(樽熟成)",
}

GRADE_PATTERN = re.compile(r"(SHB|G[1-6]|No\.\d+|Aグレード|AA)")

ROAST_KEYWORDS = {
    "ライト": "ライトロースト", "シナモン": "シナモンロースト",
    "ミディアム": "ミディアムロースト", "ハイ": "ハイロースト",
    "シティ": "シティロースト", "フルシティ": "フルシティロースト",
    "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}

# 実データ調査で判明: PHILOCOFFEAの看板ブレンド("011 TOKYO BLEND"・
# "RUDDER BLEND"等)は英語の"BLEND"表記のみで、日本語の「ブレンド」を
# 含まない商品名が多い。両方を検出できるようにする(大文字小文字は無視)。
BLEND_KEYWORDS = ["ブレンド", "blend"]

# --- フレーバーコーヒー検出マスタ ---------------------------------------------
# 焙煎時・焙煎後に人工的な香り付けを施したコーヒー。産地・精選方法・グレードの
# 個性を楽しむ「スペシャルティ/シングルオリジン」志向のアプリの趣旨とは
# 完全に異なる商品カテゴリのため、他のどの判定よりも優先して検出し区別する。
#
# 注意: 単独の「フレーバー」は含めない。「フレーバー」はテイスティングノート用語
# としても普通に使われる(例:「フルーティーフレーバーのケニア」)ため、単独語で
# マッチさせると本来ストレートコーヒーを誤ってフレーバーコーヒー扱いしてしまう
# 危険がある(実データ調査で判明)。「フレーバーコーヒー」等の複合語のみで判定する。
FLAVOR_KEYWORDS = ["フレーバーコーヒー", "フレーバー珈琲", "フレーバーコーヒー豆"]

# フレーバー名(参考情報として保持する用。判定には使わない)
FLAVOR_NAME_KEYWORDS = [
    "ココナッツ", "アーモンド", "バニラ", "ヘーゼルナッツ", "キャラメル",
    "チョコレート", "メープル", "ラム", "アマレット", "シナモン",
]

# --- テイスティングノートの見出しシノニム ---------------------------------------
# 店舗の説明文・表組みで「味わい」「風味」「フレーバー」「テイスティングノート」
# 等、見出し表記が店舗ごとに割れることが実データ調査で判明。技術的には細かい
# 定義の違いがあるが(フレーバー=口内での味+鼻孔からの香りの組み合わせ、
# 味わい=酸味・苦味・コク・後味まで含む総合的な体験、等)、店舗の実務では
# ほぼ同義語として使われているため、パース対象の見出しとして横断的に扱う。
TASTING_NOTE_LABEL_SYNONYMS = [
    "味わい", "風味", "フレーバー", "テイスティングノート", "香味",
    "tasting notes", "flavor notes", "flavour notes", "cupping notes",
]

# SCA(スペシャルティコーヒー協会)+ WCR(ワールドコーヒーリサーチ)の
# フレーバーホイール(2016年版)の9大カテゴリ。テイスティングノートの
# フリーテキストを大分類に振り分ける際の参考マスタとして使用。
SCA_FLAVOR_WHEEL_CATEGORIES = {
    "Fruity": "フルーティー",       # ベリー、ドライフルーツ、柑橘、その他フルーツ
    "Floral": "フローラル",         # ジャスミン、ローズ等
    "Sweet": "スイート/甘み",       # キャラメル、はちみつ、バニラ、ブラウンシュガー
    "Nutty/Cocoa": "ナッツ/カカオ", # アーモンド、ヘーゼルナッツ、ダーク/ミルクチョコレート
    "Spices": "スパイス",           # シナモン、クローブ、ペッパー、アニス
    "Roasted": "ロースト",          # スモーキー、タバコ、シダー、焦げ
    "Green/Vegetative": "グリーン/野菜っぽさ",  # 青草、豆っぽさ
    "Sour/Fermented": "酸味/発酵",  # ビネガー、アルコール、熟成チーズ様
    "Other": "その他",              # 紙っぽさ/カビっぽさ、ケミカル、オリーブオイル
}

# SCAフレーバーホイール(公式PDF)の外側の輪にある具体的な用語 → 大分類の対応表。
# テイスティングノートのフリーテキストから、含まれる単語を検出して大分類に
# 振り分ける用途を想定(将来的な自動タグ分類機能のためのマスタ)。
SCA_FLAVOR_WHEEL_TERMS = {
    # Fruity
    "blackberry": "Fruity", "raspberry": "Fruity", "blueberry": "Fruity", "strawberry": "Fruity",
    "raisin": "Fruity", "prune": "Fruity",
    "coconut": "Fruity", "cherry": "Fruity", "pomegranate": "Fruity", "pineapple": "Fruity",
    "grape": "Fruity", "apple": "Fruity", "peach": "Fruity", "pear": "Fruity",
    "grapefruit": "Fruity", "orange": "Fruity", "lemon": "Fruity", "lime": "Fruity",
    # Sour/Fermented
    "sour aromatics": "Sour/Fermented", "acetic acid": "Sour/Fermented",
    "butyric acid": "Sour/Fermented", "isovaleric acid": "Sour/Fermented",
    "citric acid": "Sour/Fermented", "malic acid": "Sour/Fermented",
    "winey": "Sour/Fermented", "whiskey": "Sour/Fermented",
    "fermented": "Sour/Fermented", "overripe": "Sour/Fermented",
    # Green/Vegetative
    "under-ripe": "Green/Vegetative", "peapod": "Green/Vegetative", "fresh": "Green/Vegetative",
    "dark green": "Green/Vegetative", "vegetative": "Green/Vegetative",
    "hay-like": "Green/Vegetative", "herb-like": "Green/Vegetative", "beany": "Green/Vegetative",
    "olive oil": "Green/Vegetative", "raw": "Green/Vegetative",
    # Other
    "stale": "Other", "cardboard": "Other", "papery": "Other", "woody": "Other",
    "moldy": "Other", "musty": "Other", "animalic": "Other",
    "bitter": "Other", "salty": "Other", "medicinal": "Other", "petroleum": "Other",
    "skunky": "Other", "rubber": "Other", "meaty": "Other", "brothy": "Other", "phenolic": "Other",
    "chemical": "Other",
    # Roasted
    "pipe tobacco": "Roasted", "tobacco": "Roasted",
    "acrid": "Roasted", "ashy": "Roasted", "smoky": "Roasted",
    "brown, roast": "Roasted", "grain": "Roasted", "malt": "Roasted", "cereal": "Roasted",
    # Spices
    "pungent": "Spices", "pepper": "Spices",
    "anise": "Spices", "nutmeg": "Spices", "cinnamon": "Spices", "clove": "Spices",
    "brown spice": "Spices",
    # Nutty/Cocoa
    "peanuts": "Nutty/Cocoa", "hazelnut": "Nutty/Cocoa", "almond": "Nutty/Cocoa",
    "chocolate": "Nutty/Cocoa", "dark chocolate": "Nutty/Cocoa", "cocoa": "Nutty/Cocoa",
    "nutty": "Nutty/Cocoa",
    # Sweet
    "molasses": "Sweet", "maple syrup": "Sweet", "caramelized": "Sweet", "honey": "Sweet",
    "vanilla": "Sweet", "vanillin": "Sweet", "overall sweet": "Sweet",
    "sweet aromatics": "Sweet", "black tea": "Sweet", "brown sugar": "Sweet",
    # Floral
    "chamomile": "Floral", "rose": "Floral", "jasmine": "Floral", "floral": "Floral",
}

# WCR(ワールドコーヒーリサーチ)品種カタログ(55アラビカ品種・47ロブスタ品種)より、
# 商品名・説明文で言及されやすい主要品種のみ抜粋したマスタ。品種検出の参考に使う。
# 出典: https://varieties.worldcoffeeresearch.org/
VARIETY_KEYWORDS = {
    # ティピカ系統
    "Typica": "ティピカ系統", "ティピカ": "ティピカ系統",
    "Pache": "ティピカ系統", "Kent": "ティピカ系統", "Java": "ティピカ系統",
    # ブルボン系統
    "Bourbon": "ブルボン系統", "ブルボン": "ブルボン系統",
    "SL28": "ブルボン系統", "SL34": "ブルボン系統",
    "Pacas": "ブルボン系統", "Villa Sarchi": "ブルボン系統",
    # カトゥーラ/カトゥアイ系統
    "Caturra": "カトゥーラ系統", "カトゥーラ": "カトゥーラ系統",
    "Catuai": "カトゥアイ系統", "カトゥアイ": "カトゥアイ系統",
    "Mundo Novo": "ムンドノーボ", "Maragogype": "マラゴジッペ", "Pacamara": "パカマラ",
    # サルチモール/カティモール系統(サビ病耐性の交配品種)
    "Catimor": "カティモール系統", "Sarchimor": "サルチモール系統",
    "Ruiru 11": "ルイル11", "Batian": "バティアン", "Parainema": "パライネマ",
    # 特殊・高付加価値品種
    "Geisha": "ゲイシャ", "Gesha": "ゲイシャ", "ゲイシャ": "ゲイシャ",
    "Starmaya": "スターマヤ(F1ハイブリッド)", "Marsellesa": "マルセリェーザ(F1ハイブリッド)",
    "Heirloom": "エチオピア在来種(ヘアルーム)",
}


def parse_product(raw_name: str) -> dict:
    """商品名(原文)を解析し、産地・精選方法・グレード・焙煎度等を抽出する。

    分類の優先順位: フレーバーコーヒー(最優先で区別) → ブレンド → ストレート
    産地判定の優先順位: 特定銘柄 → 国名直接表記 → 地域名逆引き
    （店舗のカテゴリ情報によるフォールバックはスクレイパー側で別途付与する）
    """
    is_flavored = any(kw in raw_name for kw in FLAVOR_KEYWORDS)

    result = {
        "raw_name": raw_name,
        "category": "フレーバー" if is_flavored
                    else ("ブレンド" if any(kw.lower() in raw_name.lower() for kw in BLEND_KEYWORDS) else "ストレート"),
        "is_flavored": is_flavored,
        "flavor_name": None,
        "origin_country": None,
        "origin_source": None,
        "designated_brand": None,
        "designated_brand_note": None,
        "processing_method": None,
        "grade": None,
        "roast_level": None,
        "post_processing_tags": [],
    }

    if is_flavored:
        # フレーバーコーヒーは産地・精選方法・グレード等の解析対象外とする
        # (ベース豆の産地表記があっても、商品の主眼は香り付けであり産地の個性ではないため)
        for kw in FLAVOR_NAME_KEYWORDS:
            if kw in raw_name:
                result["flavor_name"] = kw
                break
        return result

    # 特定銘柄
    for kw, (brand, country, exclusion) in DESIGNATED_BRAND_KEYWORDS.items():
        if kw in raw_name:
            result["designated_brand"] = brand
            result["designated_brand_note"] = exclusion
            result["origin_country"] = country
            result["origin_source"] = "brand"
            break

    # 国名直接表記(日本語)
    if not result["origin_country"]:
        for kw, country in ORIGIN_COUNTRY_KEYWORDS.items():
            if kw in raw_name:
                result["origin_country"] = country
                result["origin_source"] = "country_name"
                break

    # 国名直接表記(英語、大文字小文字無視)
    if not result["origin_country"]:
        lowered = raw_name.lower()
        for kw, country in ORIGIN_COUNTRY_KEYWORDS_EN.items():
            if kw in lowered:
                result["origin_country"] = country
                result["origin_source"] = "country_name"
                break

    # 地域名からの逆引き
    if not result["origin_country"]:
        for kw, country in REGION_TO_COUNTRY.items():
            if kw in raw_name:
                result["origin_country"] = country
                result["origin_source"] = "region_name"
                break

    # 精選方法(大文字小文字無視・日英表記ゆれ正規化)
    result["processing_method"] = detect_processing_method(raw_name)

    # 後処理タグ(複数可)
    lowered_name = raw_name.lower()
    for kw, tag in POST_PROCESSING_KEYWORDS.items():
        if kw.lower() in lowered_name and tag not in result["post_processing_tags"]:
            result["post_processing_tags"].append(tag)

    # グレード
    m = GRADE_PATTERN.search(raw_name)
    if m:
        result["grade"] = m.group(1)

    # 焙煎度
    for kw, roast in ROAST_KEYWORDS.items():
        if kw in raw_name:
            result["roast_level"] = roast
            break

    return result


def apply_category_hint_fallback(parsed: dict, category_hint: str) -> dict:
    """商品名だけで産地判定できなかった場合、店舗のカテゴリ情報で補完する。"""
    if parsed["origin_country"] or not category_hint:
        return parsed
    # カテゴリ文字列に対しても同じ国名マッチングを試みる
    for kw, country in ORIGIN_COUNTRY_KEYWORDS.items():
        if kw in category_hint:
            parsed["origin_country"] = country
            parsed["origin_source"] = "category_hint"
            break
    return parsed


# --- 商品詳細ページの説明文パース ---------------------------------------------
# Denim bisの商品詳細ページでは「精製処理：ナチュラル」「栽培品種：ムンドノーボ、
# カツカイ、カツアイ」のように、決まった書式で説明文中に情報が構造化されている
# ことが実データ確認で判明。商品名より確実に取れる場合があるため、
# 商品名パースの結果を補強・上書きする用途で使う。
#
# 用語について: 正しくは「精選」だが、実店舗の表記は「精製処理」が使われていた
# ため、両方の書式にマッチするようパターンを用意している。

DESC_PROCESSING_PATTERN = re.compile(r"(?:精選方法|精選|精製処理|精製方法)[：:]\s*([^\s、。\n]+)")
DESC_VARIETY_PATTERN = re.compile(r"栽培品種[：:]\s*([^\n]+)")


def extract_from_description(description_text: str) -> dict:
    """商品説明文から精選方法・栽培品種を抽出する。

    呼び出し側は description_text を段落(<p>タグ等)ごとに改行で連結して渡すこと。
    区切りなしで連結すると、隣接する項目(例:栽培品種の直後に精製処理が続く場合)を
    品種側の正規表現が巻き込んでしまう不具合が実データ検証で判明したため。
    """
    extra = {"processing_method": None, "variety_note": None}
    if not description_text:
        return extra

    m = DESC_PROCESSING_PATTERN.search(description_text)
    if m:
        raw_method = m.group(1)
        # PROCESSING_METHOD_SYNONYMSと照合して正規化(一致しなければ生の文字列を保持)
        extra["processing_method"] = normalize_processing_method(raw_method)

    m2 = DESC_VARIETY_PATTERN.search(description_text)
    if m2:
        extra["variety_note"] = m2.group(1).strip()

    return extra
