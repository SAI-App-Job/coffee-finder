# -*- coding: utf-8 -*-
"""
migrate_first_detected_at.py

first_detected_at(新規掲載判定用の初出検知日時)フィールド導入時の一回限りの
移行スクリプト。data/products.jsonの既存レコード(このフィールド導入前に
生成されたもの)にMIGRATION_FALLBACK_FIRST_DETECTED_AT(記録開始日)を
遡及的に割り当てる。

通常運用では、aggregate_shops.pyのresolve_first_detected_at()が毎回の
集約時に同じロジックを適用するため、このスクリプトは初回導入時に一度だけ
実行すればよい(以後は新規スクレイピングのたびに自然と正しく割り当てられる)。

実行方法: python migrate_first_detected_at.py
"""

import json

from aggregate_shops import DATA_DIR, MIGRATION_FALLBACK_FIRST_DETECTED_AT


def main():
    path = DATA_DIR / "products.json"
    with path.open(encoding="utf-8") as f:
        products = json.load(f)

    migrated = 0
    for product in products:
        if not product.get("first_detected_at"):
            product["first_detected_at"] = MIGRATION_FALLBACK_FIRST_DETECTED_AT
            migrated += 1

    with path.open("w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[done] {migrated}/{len(products)}件にfirst_detected_atを遡及的に割り当てました")


if __name__ == "__main__":
    main()
