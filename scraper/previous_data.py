# -*- coding: utf-8 -*-
"""
previous_data.py

差分ベーススクレイピングのための共通ヘルパー。各スクレイパーは一覧ページ
(軽量)だけを取得した後、コミット済みの /data/products.json にある自店舗の
既存レコードと突き合わせ、「新商品」または「一覧上で価格・在庫状況が
前回と変わった商品」だけ詳細ページを再取得する。一覧の時点で前回と
変化がないと判断できた商品は、/data/products.json の既存レコードを
そのまま使い回す。

【重要】load_previous_products()が返すレコードは、各スクレイパー自身の
生スキーマではなく /data/products.json の集約後スキーマ(snake_case、
aggregate_shops.pyのbuild_product()が読むキー名)である。両者はほぼ
同じキー名を使っているため(origin_country/processing_method/roast_level等)、
このレコードをそのまま各スクレイパーのrecordsリストに混ぜてもaggregate_shops.py
側で問題なく再集約できる。例外はfarm_note(生スキーマ側は複数の細かい
フィールドから合成するが、集約後は1つの文字列になっている)で、これは
aggregate_shops.py のcompose_farm_note()側で「既にfarm_noteがあればそれを
優先する」形で吸収している。
"""

import json
from pathlib import Path

DATA_PRODUCTS_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"


def load_previous_products(shop_name: str) -> dict:
    """product_urlをキーに、指定店舗の既存レコード(dict)を返す。
    data/products.jsonが存在しない/読めない場合は空辞書を返す
    (=すべて新規として扱われ、これまで通り全件詳細ページを取得する)。"""
    if not DATA_PRODUCTS_PATH.exists():
        return {}
    try:
        with DATA_PRODUCTS_PATH.open(encoding="utf-8") as f:
            products = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        p["product_url"]: p
        for p in products
        if p.get("shop_name") == shop_name and p.get("product_url")
    }


def is_unchanged(prev: dict | None, *, raw_name: str, **list_fields) -> bool:
    """一覧ページの情報(raw_name + 店舗ごとの価格・在庫フィールド)が
    前回のレコードと一致するかを判定する。フレーバーコーヒーは判定対象外
    (常に「変化あり」= 通常の解析ルートを通す)。"""
    if not prev:
        return False
    if prev.get("is_flavored") or prev.get("category") == "フレーバー":
        return False
    if prev.get("raw_name") != raw_name:
        return False
    return all(prev.get(key) == value for key, value in list_fields.items())
