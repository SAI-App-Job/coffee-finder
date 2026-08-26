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
# 注意: 「タイ」(タイ王国)は意図的にここへ含めていない。2文字と短いため、
# 「ディップ**スタイ**ル」(style)や「ガ**タイ**ティ」(Gathaiti、ケニアの
# 地名の音写)のような無関係な語の部分文字列に大量に誤爆することが実データ
# 調査で判明した(現在の全件データで、この経路によるタイ産判定は0/3件が
# 誤検出という結果だった)。英語表記"thailand"(ORIGIN_COUNTRY_KEYWORDS_EN)は
# 十分に長く衝突しないため、そちらのみで検出する。
ORIGIN_COUNTRY_KEYWORDS = {
    "ベトナム": "ベトナム",
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
    "ニカラグア": "ニカラグア",  # 実データ確認済み(Rhizomag)。英語表記("nicaragua")は
    # ORIGIN_COUNTRY_KEYWORDS_ENに既にあったが、日本語表記がJP側の辞書に無く未検出だった。
    "コンゴ": "コンゴ民主共和国",  # 実データ確認済み(珈琲丸)。コンゴ共和国(Republic of
    # the Congo)よりコンゴ民主共和国(旧ザイール)の方がスペシャルティコーヒーでは
    # 一般的なため、こちらを既定の変換先とする。
    "エルサルバドル": "エルサルバドル",  # 実データ確認済み(TSUKIKOYA COFFEE ROASTER)。
    # 英語表記("el salvador")はORIGIN_COUNTRY_KEYWORDS_ENに既にあったが、
    # 日本語カタカナ表記がJP側の辞書に無く未検出だった(ニカラグアと同種の抜け)。
    "インド": "インド",  # 実データ確認済み(TSUKIKOYA COFFEE ROASTER、"INDIA Balmaadi"の
    # 日本語表記想定)。「インドネシア」の部分文字列になるため、dictの挿入順で
    # 必ず「インドネシア」より後ろに置くこと(先に置くとインドネシア産の商品を
    # 誤ってインド産と判定してしまう)。
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
    "thailand": "タイ", "dr congo": "コンゴ民主共和国", "congo": "コンゴ民主共和国",
    "dominica": "ドミニカ国",
    "india": "インド",  # 実データ確認済み(TSUKIKOYA COFFEE ROASTER、"INDIA Balmaadi"表記)
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
    "ガヨ": "インドネシア",
    "コナ": "アメリカ(ハワイ)", "シグリ": "パプアニューギニア",
    # 注意: 「バリ」(インドネシア・バリ島)は意図的にここへ含めていない。2文字と短く、
    # 「バリスタ」(barista、実データ確認済み: Rhizomagのコーヒーミル商品「ザッセンハウス
    # バリスタプロ」が誤ってインドネシア産と判定された)のような無関係な語に部分文字列で
    # 誤爆するため。ORIGIN_COUNTRY_KEYWORDSの「タイ」除外と同じ理由・同じ対策。
    "ハラバコア": "ドミニカ共和国",
    "Los Pirineos": "エルサルバドル",  # Finca Los Pirineos(パカマラ種の発祥農園として知られる)
}

# --- 特定銘柄マスタ(全日本コーヒー公正取引協議会 14銘柄) ----------------------
DESIGNATED_BRAND_KEYWORDS = {
    "ブルーマウンテン": ("ブルーマウンテン", "ジャマイカ", None),
    "ブルー・マウンテン": ("ブルーマウンテン", "ジャマイカ", None),  # 実データ確認済み(Rhizomag)。
    # 中黒(・)入りの表記ゆれ。dictは挿入順で先勝ちのため、中黒なしの正規表記より後ろに置いても
    # 実害はない(両方とも同じ値を指すため、どちらが先にマッチしても結果は同じ)。
    "ハイマウンテン": ("ハイマウンテン", "ジャマイカ", None),
    "クリスタルマウンテン": ("クリスタルマウンテン", "キューバ", None),
    "アンティグア": ("グアテマラアンティグア", "グアテマラ", None),
    "コロンビアスプレモ": ("コロンビアスプレモ", "コロンビア", None),
    "モカハラー": ("モカ・ハラー", "エチオピア", None),
    "モカマタリ": ("モカ・マタリ", "イエメン", None),
    "キリマンジャロ": ("キリマンジャロ", "タンザニア", "ブコバ地区産を除く"),
    "キリマンジェロ": ("キリマンジャロ", "タンザニア", "ブコバ地区産を除く"),  # 実データ確認済み(楽園)。
    # 店舗表記の誤字(「ジャ」→「ジェ」)だが、実際に使われている表記のため検出対象に含める。
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


# --- 在庫状態マスタ(日英表記ゆれの正規化) ------------------------------------
# 店舗によって在庫状態の表記が「終売」「完売」「SOLD OUT」等バラバラな上、
# 「終売」(再入荷なし)と「完売」(再入荷の可能性あり)のように意味の異なる
# 状態が同じ「品切れ」として扱われがちなことが実データ調査で判明した。
# PROCESSING_METHOD_SYNONYMSと同じ発想で、data/stock_status_synonyms.json
# を唯一の情報源として3段階(終売/一時的に品切れ/販売中)に正規化する。
_STOCK_STATUS_SYNONYMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "stock_status_synonyms.json"
)
with open(_STOCK_STATUS_SYNONYMS_PATH, encoding="utf-8") as _f:
    _STOCK_STATUS_MASTER = json.load(_f)

STOCK_STATUS_SYNONYMS = {
    canonical: entry["synonyms"] for canonical, entry in _STOCK_STATUS_MASTER.items()
}

# 「まもなく終売」(近日終売予定、現時点ではまだ購入可能)のように、「終売」を
# 含みながら実際にはまだ販売中の予告表現が実データ調査で見つかった(該当2件とも
# div.sold_out要素が存在せず、実際に購入可能なことを確認済み)。この予告表現を
# 先に取り除いてから判定することで、「終売」という単語自体は含むが実際は
# まだ終売していない商品を誤って終売と判定しないようにする。
STOCK_STATUS_NOT_YET_PATTERNS = ["まもなく終売"]


def detect_stock_status(raw_name, structural_out_of_stock=False):
    """商品名のテキストと、店舗サイトの構造化された在庫フラグ(取得できる場合)を
    組み合わせて、在庫状態を「終売」「一時的に品切れ」「販売中」の3段階に正規化する。

    優先順位: (1)商品名に「終売」相当の表記があれば終売、(2)商品名に「完売」
    相当の表記があれば一時的に品切れ、(3)店舗サイト側の構造化された品切れ
    フラグ(structural_out_of_stock)が立っていれば一時的に品切れ、
    (4)いずれでもなければ販売中。

    商品名のテキストを構造化フラグより先に見る理由: PHILOCOFFEAは商品名に
    「終売」「完売」を明記する一方、一覧ページの品切れ表示要素はHTMLコメント内
    にしか存在せず(実データ調査で判明、常にコメントアウトされておりBeautiful
    Soupのタグ検索では絶対にヒットしない)、構造化フラグが実質的に機能して
    いない。商品名のテキストの方が確実な一次情報となる店舗があるため。
    """
    sanitized = raw_name or ""
    for pattern in STOCK_STATUS_NOT_YET_PATTERNS:
        sanitized = sanitized.replace(pattern, "")
    lowered = sanitized.lower()

    for kw in STOCK_STATUS_SYNONYMS.get("終売", []):
        if kw.lower() in lowered:
            return "終売"
    for kw in STOCK_STATUS_SYNONYMS.get("一時的に品切れ", []):
        if kw.lower() in lowered:
            return "一時的に品切れ"
    if structural_out_of_stock:
        return "一時的に品切れ"
    return "販売中"


# --- 後処理タグマスタ --------------------------------------------------------
POST_PROCESSING_KEYWORDS = {
    "バレルエイジド": "バレルエイジド(樽熟成)",
    "樽熟成": "バレルエイジド(樽熟成)",
    "barrel aged": "バレルエイジド(樽熟成)",
    "whiskey barrel": "バレルエイジド(樽熟成)",  # 実データ確認済み(TSUKIKOYA COFFEE ROASTER)。
    # 「WHISKEY BARREL」という商品名表記のみで「barrel aged」を含まないため別途追加
}

GRADE_PATTERN = re.compile(r"(SHB|SHG|G-?[1-6]|No\.\d+|Aグレード|AA)")
# SHG(Strictly High Grown)は実データ確認済み(2026-08時点、Coulaneの「ニカラグア SHG
# キータスウエノス農園」等)。コスタリカ・グアテマラ・ホンジュラス・エルサルバドル・
# ニカラグア等、標高で格付けする複数国で使われる表記でSHBの兄弟格にあたるが、
# これまでの実データにSHG表記の商品が無かったため未対応のままだった。
# G-1のようなハイフン付き表記も実データ確認済み(2026-08時点、カフェクラウディアの
# 「エチオピア ベンチ・マジG-1 ゲシャ・カルマチ農園」等)。マッチ後にparse_product()側で
# ハイフンを除去し、ハイフン無し表記(G1)と同じ値に正規化する(表示上の見た目を揃え、
# フィルタ等で同一グレードが別値として分裂しないようにするため)。

# --- コロンビア産グレードマスタ(FNC公式: cafedecolombia.jp/colombia/specialty/grade/) --
# 「エクセルソ(Excelso)」は7サブグレード共通の親カテゴリ名であり、単独では
# 商品を特定できない(スクリーンサイズにより意味が変わる)。そのため実データの
# 商品名にはサブグレード名(スプレモ等)のみが書かれ、「エクセルソ」自体が
# 省略されているケースが多い(実データ確認済み: COFFEE ROASTERY MEGUROの
# 「コロンビア　スプレモ」は商品名に「エクセルソ」を含まない)。よって判定は
# サブグレード名の検出を起点にし、見つかった場合のみ「エクセルソ+サブ名」の
# 複合語を組み立てて返す(サブグレードが特定できない「エクセルソ」単独の
# 表記は、7グレードのどれを指すか商品名からは判別できないため、あえてタグを
# 付与しない)。「エクセルソ」「エキセルソ」の表記ゆれは、常にこちら側で
# 「エクセルソ」に正規化して組み立てるため、シノニム辞書に別途持つ必要はない。
_COLOMBIA_GRADE_SYNONYMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "colombia_grade_synonyms.json"
)
with open(_COLOMBIA_GRADE_SYNONYMS_PATH, encoding="utf-8") as _f:
    _COLOMBIA_GRADE_MASTER = json.load(_f)

COLOMBIA_GRADE_SYNONYMS = {
    canonical: entry["synonyms"] for canonical, entry in _COLOMBIA_GRADE_MASTER.items()
}


def detect_colombia_grade(text):
    """コロンビア産商品のテキストからFNCのサブグレードを検出し、
    「エクセルソ+サブ名」の複合語として返す(検出できなければNone)。
    """
    if not text:
        return None
    lowered = text.lower()
    for canonical, synonyms in COLOMBIA_GRADE_SYNONYMS.items():
        for kw in synonyms:
            if kw.lower() in lowered:
                return f"エクセルソ {canonical}"
    return None

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


def detect_country_name(text: str) -> str | None:
    """テキスト中の国名直接表記(日本語→英語の順)を検出する。特定銘柄・地域名
    逆引きは含まない、素の国名マッチングのみの軽量版(parse_product()と、
    ブレンド商品のBEANS DATA表の産地グループ見出し(例:"Kenya Kariaini")
    から国名部分だけを取り出す用途の両方で共有する)。
    """
    if not text:
        return None
    for kw, country in ORIGIN_COUNTRY_KEYWORDS.items():
        if kw in text:
            return country
    lowered = text.lower()
    for kw, country in ORIGIN_COUNTRY_KEYWORDS_EN.items():
        if kw in lowered:
            return country
    return None


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

    # 国名直接表記(日本語→英語の順)
    if not result["origin_country"]:
        country = detect_country_name(raw_name)
        if country:
            result["origin_country"] = country
            result["origin_source"] = "country_name"

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

    # グレード(コロンビア産はFNC公式のサブグレード名から「エクセルソ+サブ名」を
    # 組み立てる。それ以外の産地は従来通りGRADE_PATTERNの一般的な等級表記に従う)
    if result["origin_country"] == "コロンビア":
        result["grade"] = detect_colombia_grade(raw_name)
    else:
        m = GRADE_PATTERN.search(raw_name)
        if m:
            result["grade"] = re.sub(r"^G-(\d)$", r"G\1", m.group(1))

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
    # 産地がカテゴリ情報からしか判明しなかった場合、parse_product内では
    # まだコロンビアと確定していないためグレード判定が走っていない。
    # ここで改めて商品名からのコロンビアグレード検出を試みる。
    if parsed["origin_country"] == "コロンビア" and not parsed["grade"]:
        parsed["grade"] = detect_colombia_grade(parsed["raw_name"])
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
