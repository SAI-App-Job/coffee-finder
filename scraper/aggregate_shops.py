# -*- coding: utf-8 -*-
"""
aggregate_shops.py

scrape_denimbis.py / scrape_millcoffee.py / scrape_philocoffea.py が出力する
data_denimbis.json / data_millcoffee.json / data_philocoffea.json を統合し、
docs/coffee-app-data-model.md 準拠のスキーマで /data/shops.json と
/data/products.json を更新する。

【店舗ごとに出力フィールドが異なる理由】
各スクレイパーはサイト構造(Ocnk/Wix/カラーミーショップ)に依存しており、
取得できる情報がまちまち(例: Denim bisはprice_min/price_max、MiLL Coffee/
PHILOCOFFEAは単一price。PHILOCOFFEAのみBEANS DATA表からflavor_notes・
producer_name等のPRODUCER_LOT相当の情報が取れる)。本スクリプトはこれらを
共通スキーマへ正規化し、スクレイパーが取得できない項目はnullのまま保持する
(存在しない情報を推測・創作しない)。

【営業時間・地図クエリ・実店舗一覧を上書きしない理由】
hours(営業時間)・map_query(Googleマップ検索用クエリ)・locations(実店舗一覧)・
shop_typeはいずれもスクレイパーが取得しない情報(店舗の基本ページに営業時間の
構造化データがない等)。既存のdata/shops.jsonの値をそのまま引き継ぎ、
スクレイパーが実際に取得する項目(name/url/platform/address/prefecture/
robots_txt_status)のみを更新する。

【タイムスタンプの扱い】
last_scraped_at/scraped_atを毎回の実行時刻でナイーブに上書きすると、内容に
変化がなくてもファイルが毎回差分を持ってしまい、「変化がなければコミットしない」
というワークフロー側の意図が壊れる。そのため、タイムスタンプ以外の内容が
前回コミット時と同一の場合は、タイムスタンプも前回の値をそのまま引き継ぐ
(stabilize_timestampで比較・引き継ぎを行う)。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRAPER_DIR.parent / "data"

SOURCE_FILES = {
    "Denim bis": "data_denimbis.json",
    "MiLL Coffee": "data_millcoffee.json",
    "PHILOCOFFEA": "data_philocoffea.json",
}


def load_source(shop_name: str) -> dict:
    path = SCRAPER_DIR / SOURCE_FILES[shop_name]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が見つかりません({shop_name}のスクレイパーが正常終了したか確認してください)"
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def stabilize_timestamp(new_obj: dict, old_obj: dict | None, field: str) -> None:
    """new_objとold_objが指定フィールド以外まったく同じ内容なら、
    new_obj[field]をold_obj[field]に差し戻す(=前回コミットとの差分をゼロにする)。"""
    if not old_obj:
        return
    new_copy = {k: v for k, v in new_obj.items() if k != field}
    old_copy = {k: v for k, v in old_obj.items() if k != field}
    if new_copy == old_copy:
        new_obj[field] = old_obj.get(field)


def build_map_query(existing_shop: dict | None, fallback_name: str) -> str:
    if existing_shop and existing_shop.get("map_query"):
        return existing_shop["map_query"]
    return fallback_name


def merge_shop(scraped_shop_info: dict, existing_shop: dict | None, now_iso: str) -> dict:
    merged = {
        "name": scraped_shop_info["name"],
        "url": scraped_shop_info.get("url"),
        "platform": scraped_shop_info.get("platform"),
        "shop_type": (existing_shop or {}).get("shop_type", "single_location"),
        "robots_txt_status": scraped_shop_info.get("robots_txt_status"),
        "address": scraped_shop_info.get("address") or (existing_shop or {}).get("address"),
        "prefecture": scraped_shop_info.get("prefecture") or (existing_shop or {}).get("prefecture"),
        "hours": (existing_shop or {}).get("hours"),
        "map_query": build_map_query(existing_shop, scraped_shop_info["name"]),
        "last_scraped_at": now_iso,
    }
    if existing_shop and existing_shop.get("locations"):
        merged["locations"] = existing_shop["locations"]
    stabilize_timestamp(merged, existing_shop, "last_scraped_at")
    return merged


def normalize_category_hint(value) -> str | None:
    if isinstance(value, list):
        return "/".join(value) if value else None
    return value


def compose_farm_note(record: dict) -> str | None:
    """farm_note(自由記述)は、スクレイパーが取得したPRODUCER_LOT相当の断片
    (生産者名・農園名・地区・標高・品種)をそのまま連結して作る。存在しない
    項目は含めない(推測で埋めない)。"""
    parts = []
    if record.get("farm_name"):
        parts.append(f"農園: {record['farm_name']}")
    producer = record.get("producer_name") or record.get("producer_note")
    if producer:
        parts.append(f"生産者: {producer}")
    if record.get("region_detail"):
        parts.append(f"エリア: {record['region_detail']}")
    if record.get("altitude_min_m") and record.get("altitude_max_m"):
        parts.append(f"標高: {record['altitude_min_m']}-{record['altitude_max_m']}m")
    elif record.get("altitude_note"):
        parts.append(f"標高: {record['altitude_note']}")
    variety = record.get("variety") or record.get("variety_note")
    if variety:
        parts.append(f"品種: {variety}")
    return "、".join(parts) if parts else None


def infer_roast_selectable(record: dict) -> bool:
    if "roast_selectable" in record:
        return bool(record["roast_selectable"])
    # PHILOCOFFEAはroast_selectableを出力しないため、Denim bis/MiLL Coffeeと同じ
    # ヒューリスティック(焙煎度が取れておらずストレート豆)で推定する
    return record.get("roast_level") is None and record.get("category") == "ストレート"


def build_product_id(record: dict) -> str:
    # product_urlは全店舗共通で一意・再実行間でも安定しているため、そのままIDとして使う
    if record.get("product_url"):
        return record["product_url"]
    return f"{record['shop_name']}:{record['raw_name']}"


def build_product(record: dict, shop_map_query: str, now_iso: str) -> dict:
    return {
        "id": build_product_id(record),
        "shop_name": record["shop_name"],
        "raw_name": record["raw_name"],
        "category": record.get("category"),
        "is_flavored": bool(record.get("is_flavored") or record.get("category") == "フレーバー"),
        "flavor_name": record.get("flavor_name"),
        "category_hint": normalize_category_hint(record.get("category_hint")),
        "origin_country": record.get("origin_country"),
        "origin_source": record.get("origin_source"),
        "designated_brand": record.get("designated_brand"),
        "processing_method": record.get("processing_method"),
        "grade": record.get("grade"),
        "roast_level": record.get("roast_level"),
        "roast_selectable": infer_roast_selectable(record),
        "roast_hint": record.get("roast_hint"),
        "farm_note": compose_farm_note(record),
        "flavor_notes": record.get("flavor_notes"),
        "price": record.get("price"),
        "price_min": record.get("price_min"),
        "price_max": record.get("price_max"),
        "weight_g": None,  # 現行スクレイパーはいずれも重量(g)を抽出していない
        "unit_note": record.get("unit_note"),
        "out_of_stock": bool(record.get("out_of_stock", False)),
        "decaf_process": record.get("decaf_process"),
        "product_url": record.get("product_url"),
        "map_query": shop_map_query,
        "scraped_at": now_iso,
    }


def main():
    now_iso = datetime.now(timezone.utc).isoformat()

    existing_shops_list = load_json_list(DATA_DIR / "shops.json")
    existing_shops = {s["name"]: s for s in existing_shops_list}
    existing_products = {p["id"]: p for p in load_json_list(DATA_DIR / "products.json")}

    merged_shops_by_name = {}
    all_products = []

    for shop_name in SOURCE_FILES:
        source = load_source(shop_name)
        existing_shop = existing_shops.get(shop_name)

        merged_shop = merge_shop(source["shop"], existing_shop, now_iso)
        merged_shops_by_name[shop_name] = merged_shop

        for record in source.get("products", []):
            # フレーバーコーヒーは産地・精選方法の個性を扱う本アプリの趣旨と異なるため
            # 通常商品一覧には出さない(docs/coffee-app-data-model.md 15章の方針)
            if record.get("is_flavored") or record.get("category") == "フレーバー":
                continue
            product = build_product(record, merged_shop["map_query"], now_iso)
            stabilize_timestamp(product, existing_products.get(product["id"]), "scraped_at")
            all_products.append(product)

    # このワークフローがスクレイピング対象としない店舗(例: 珈琲問屋。対応する
    # scrape_*.pyがまだ無い)の商品は、上書きせず既存のレコードをそのまま残す
    scraped_shop_names = set(SOURCE_FILES.keys())
    for product in existing_products.values():
        if product.get("shop_name") not in scraped_shop_names:
            all_products.append(product)

    # 既存の店舗の並び順を維持しつつ、今回のスクレイパー対象外の店舗(将来増える想定)は
    # 既存レコードのまま残す
    ordered_shops = []
    seen = set()
    for name, shop in existing_shops.items():
        ordered_shops.append(merged_shops_by_name.get(name, shop))
        seen.add(name)
    for name, shop in merged_shops_by_name.items():
        if name not in seen:
            ordered_shops.append(shop)

    DATA_DIR.mkdir(exist_ok=True)
    with (DATA_DIR / "shops.json").open("w", encoding="utf-8") as f:
        json.dump(ordered_shops, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with (DATA_DIR / "products.json").open("w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[done] shops={len(ordered_shops)}件, products={len(all_products)}件 を data/ に出力しました")


if __name__ == "__main__":
    main()
