# -*- coding: utf-8 -*-
"""
aggregate_shops.py

scrape_denimbis.py / scrape_millcoffee.py / scrape_philocoffea.py /
scrape_fuglen.py が出力する data_denimbis.json / data_millcoffee.json /
data_philocoffea.json / data_fuglen.json を統合し、docs/coffee-app-data-model.md
準拠のスキーマで /data/shops.json と /data/products.json を更新する。

【店舗ごとに出力フィールドが異なる理由】
各スクレイパーはサイト構造(Ocnk/Wix/カラーミーショップ/Shopify)に依存しており、
取得できる情報がまちまち(例: Denim bisはprice_min/price_max、MiLL Coffee/
PHILOCOFFEA/FUGLENは単一price。PHILOCOFFEA・FUGLENはBEANS DATA相当の表から
flavor_notes・producer_name等のPRODUCER_LOT相当の情報が取れる)。本スクリプトは
これらを共通スキーマへ正規化し、スクレイパーが取得できない項目はnullのまま
保持する(存在しない情報を推測・創作しない)。

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

【手動入力データ(scraper/manual/shops/*.json)の扱い】
公式サイトを持たずスクレイピング対象にできない店舗(Instagram/Googleマップ
のみで営業している等)は、scraper/manual/README.mdの運用に従い
scraper/manual/shops/配下に手動でJSONを置く。このスクリプトは毎回の実行時に
このディレクトリも読み込み、data_source: "manual" のタグを保持したまま
data/shops.json・data/products.jsonへマージする。手動データは実際の
スクレイピング(data_*.json)とは無関係に処理されるため、対応するスクレイパー
が無くても取り込まれる。値は人間が確認・入力したものをそのまま使うため、
scraped_at/last_scraped_atのような自動タイムスタンプは付与しない
(代わりに人間が更新するlast_verified_atをそのまま保持する)。

【一部店舗のみ実行された場合の扱い】
scrape-shops.ymlのworkflow_dispatchでshopを1店舗に絞って実行した場合(特定の
バグ修正の検証時など)や、いずれかの店舗のスクレイパーが失敗した場合、対応する
data_*.jsonが存在しないことがある。その場合はエラーにせず、その店舗の既存の
shops.json/products.jsonのレコードをそのまま変更せず残す(load_source()参照)。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRAPER_DIR.parent / "data"
MANUAL_SHOPS_DIR = SCRAPER_DIR / "manual" / "shops"

SOURCE_FILES = {
    "Denim bis": "data_denimbis.json",
    "MiLL Coffee": "data_millcoffee.json",
    "PHILOCOFFEA": "data_philocoffea.json",
    "FUGLEN COFFEE ROASTERS": "data_fuglen.json",
    "Roast Design Coffee": "data_roastdesign.json",
    "珈琲丸": "data_coffeemaru.json",
    "豆コネクト": "data_mameconnect.json",
    "楽園": "data_rakuen.json",
    "Rhizomag": "data_rhizomag.json",
}


def load_source(shop_name: str) -> dict | None:
    """該当店舗のスクレイパー出力を読み込む。ファイルが無い場合はNoneを返す
    (ワークフロー側でshopを絞って一部店舗だけ実行した場合や、その店舗の
    ジョブが失敗した場合を想定。呼び出し側は既存データをそのまま残す)。"""
    path = SCRAPER_DIR / SOURCE_FILES[shop_name]
    if not path.exists():
        print(f"[info] {path} が見つからないため、{shop_name}は今回スキップします(既存データを保持)")
        return None
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
    項目は含めない(推測で埋めない)。

    差分ベーススクレイピングで前回のレコード(=既にfarm_noteを持つ集約後
    スキーマ)がそのまま渡ってくる場合は、断片から再合成せずそれを優先する
    (断片フィールドが無いため再合成すると空になってしまうため)。"""
    if record.get("farm_note"):
        return record["farm_note"]
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
    if record.get("harvest_note"):
        parts.append(f"収穫時期: {record['harvest_note']}")
    if record.get("grade_note"):  # 珈琲丸の「規格」欄(例:「キブ3 スクリーン15UP」)
        parts.append(f"規格: {record['grade_note']}")
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
    # stock_status(販売中/一時的に品切れ/終売)を唯一の情報源とし、out_of_stockは
    # そこから機械的に導出する(スクレイパー側が個別にout_of_stockを設定し忘れても
    # ここで矛盾なく揃う)。値が無い場合(未対応店舗等)は販売中として扱う。
    stock_status = record.get("stock_status") or "販売中"
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
        # ブレンドの産地別内訳。各要素はorigin_country/percentage/producer/farm/
        # variety/altitude/processing_methodを持つが、判明した項目のみ埋まる
        # (欠けている項目は単にnullのまま)。店舗ごとに公開情報の粒度が大きく
        # 異なる(PHILOCOFFEAは表形式で農園・品種等まで、Denim bis/MiLL Coffeeは
        # 産地国名のみ言及されることが多い)ため、産地国しか埋まらない、あるいは
        # 空配列のままの商品があるのは想定通りの挙動。FUGLENは現時点でブレンド
        # 商品自体を扱っていないため未対応(実データが無く構造を検証できない)。
        "blend_components": record.get("blend_components") or [],
        "price": record.get("price"),
        "price_min": record.get("price_min"),
        "price_max": record.get("price_max"),
        # 価格が店舗サイトに一切掲載されていない場合の案内文(例:豆コネクトの
        # 「価格は店舗にお問い合わせください」)。price系が全てnullの店舗でのみ設定される。
        "price_note": record.get("price_note"),
        "weight_g": record.get("weight_g"),  # FUGLENはバリアントのgramsから取得できる。他店舗はnullのまま
        "unit_note": record.get("unit_note"),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "decaf_process": record.get("decaf_process"),
        "product_url": record.get("product_url"),
        "map_query": shop_map_query,
        "scraped_at": now_iso,
    }


def load_manual_shop_files() -> list[Path]:
    if not MANUAL_SHOPS_DIR.exists():
        return []
    # TEMPLATE.json自体は manual/ 直下にありshops/配下には置かない運用のため、
    # ここではshops/内の*.jsonをそのまま全件対象にすればよい
    return sorted(MANUAL_SHOPS_DIR.glob("*.json"))


def build_manual_shop(raw_shop: dict) -> dict:
    return {
        "name": raw_shop["name"],
        "url": raw_shop.get("url"),
        "instagram_url": raw_shop.get("instagram_url"),
        "platform": raw_shop.get("platform"),
        "shop_type": raw_shop.get("shop_type", "single_location"),
        "address": raw_shop.get("address"),
        "prefecture": raw_shop.get("prefecture"),
        "hours": raw_shop.get("hours"),
        "map_query": raw_shop.get("google_maps_query") or raw_shop["name"],
        "data_source": "manual",
        "source_note": raw_shop.get("source_note"),
        "last_verified_at": raw_shop.get("last_verified_at"),
    }


def build_manual_product(
    raw_product: dict, shop_id: str, shop_name: str, shop_map_query: str, shop_source_note: str | None
) -> dict:
    return {
        # 手動データにはproduct_urlが無いため、店舗スラッグ+商品名で安定したIDを作る
        "id": f"manual:{shop_id}:{raw_product['raw_name']}",
        "shop_name": shop_name,
        "raw_name": raw_product["raw_name"],
        "category": "ストレート",
        "is_flavored": False,
        "flavor_name": None,
        "category_hint": None,
        "origin_country": raw_product.get("originCountry"),
        "origin_source": None,
        "designated_brand": None,
        "processing_method": raw_product.get("processingMethod"),
        "grade": None,
        "roast_level": raw_product.get("roast"),
        "roast_selectable": False,
        "roast_hint": None,
        "farm_note": raw_product.get("farmNote"),
        "flavor_notes": raw_product.get("flavorNotes"),
        "blend_components": [],
        "price": raw_product.get("price"),
        "price_min": None,
        "price_max": None,
        "price_note": None,
        "weight_g": raw_product.get("weightG"),
        "unit_note": None,
        "stock_status": "販売中",  # 手動入力は人間が確認済みの状態のみ登録する運用のため固定
        "out_of_stock": False,
        "decaf_process": None,
        "product_url": None,
        "map_query": shop_map_query,
        "scraped_at": None,
        "data_source": "manual",
        "source_note": raw_product.get("source_note") or shop_source_note,
    }


def main():
    now_iso = datetime.now(timezone.utc).isoformat()

    existing_shops_list = load_json_list(DATA_DIR / "shops.json")
    existing_shops = {s["name"]: s for s in existing_shops_list}
    existing_products = {p["id"]: p for p in load_json_list(DATA_DIR / "products.json")}

    merged_shops_by_name = {}
    all_products = []
    covered_shop_names = set()

    for shop_name in SOURCE_FILES:
        source = load_source(shop_name)
        if source is None:
            # 今回スクレイピング対象外だった店舗(shopを絞った手動実行、または
            # そのジョブが失敗した場合)。既存データを一切変更せず残す
            continue
        existing_shop = existing_shops.get(shop_name)

        merged_shop = merge_shop(source["shop"], existing_shop, now_iso)
        merged_shops_by_name[shop_name] = merged_shop
        covered_shop_names.add(shop_name)

        for record in source.get("products", []):
            # フレーバーコーヒーは産地・精選方法の個性を扱う本アプリの趣旨と異なるため
            # 通常商品一覧には出さない(docs/coffee-app-data-model.md 15章の方針)
            if record.get("is_flavored") or record.get("category") == "フレーバー":
                continue
            product = build_product(record, merged_shop["map_query"], now_iso)
            stabilize_timestamp(product, existing_products.get(product["id"]), "scraped_at")
            all_products.append(product)

    # 手動入力の店舗(公式サイトを持たずスクレイピング対象にできない店舗)。
    # 週次の自動スクレイピングとは無関係に、毎回scraper/manual/shops/*.jsonを
    # 読み込んでマージする
    for manual_path in load_manual_shop_files():
        with manual_path.open(encoding="utf-8") as f:
            manual_data = json.load(f)
        raw_shop = manual_data["shop"]
        shop_id = raw_shop.get("id") or manual_path.stem
        shop_name = raw_shop["name"]

        manual_shop = build_manual_shop(raw_shop)
        merged_shops_by_name[shop_name] = manual_shop
        covered_shop_names.add(shop_name)

        for raw_product in manual_data.get("products", []):
            all_products.append(
                build_manual_product(
                    raw_product, shop_id, shop_name, manual_shop["map_query"], manual_shop.get("source_note")
                )
            )

    # このワークフローが対象としない店舗(自動スクレイパーも手動ファイルも無い。
    # 例: 珈琲問屋)の商品は、上書きせず既存のレコードをそのまま残す
    for product in existing_products.values():
        if product.get("shop_name") not in covered_shop_names:
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
