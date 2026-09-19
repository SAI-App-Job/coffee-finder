# -*- coding: utf-8 -*-
"""
scrape_mountcoffee.py

MOUNT COFFEE(mount-coffee.myshopify.com、広島県広島市西区庚午北2-20-13-1F、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify(/products.json
全件取得方式)。

【住所について】
候補リストの「広島県広島市西区庚午北2-20-13」を、公式ストアの特定商取引法
ページ(https://mount-coffee.myshopify.com/policies/legal-notice)で実データ
確認したところ「広島県 広島市 西区庚午北2-20-13-1F」(号室情報付き)であることを
確認した(2026-09時点)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準テンプレート)。
制限なし。

【非常に特殊な商品構成について】
実データ確認済み(2026-09時点、全141件): この店はコーヒー豆販売に加えて、
「本×コーヒー」のペアリング企画(『書名／著者』とコーヒー、価格は書籍込みの
セット価格)を主力商品として展開しており、これが全商品の半数近くを占める。
これらは書名を示す鉤括弧「『』」で必ずタイトルが始まる(実データ全件で確認済み、
例外なし)ため、タイトルが『で始まる商品は一律除外する(コーヒー豆単体の
商品名は『で始まらない)。

その他の非コーヒー豆商品(実データ確認済み):
  - YAMABON(フリーペーパー/ZINE、号数のみで豆の指定なし)
  - 各種ギフト(夏ギフト・ギフトボックス・クリックポスト対応お試しセット)
  - ドリップバッグ単体商品(Drip Bag Np/袋。豆そのものではなく個包装済み
    ドリップバッグの形態)
  - 水出し用コーヒーバッグ(50g×3等、ティーバッグ状の水出し専用パック)
  - 定期便・定期購入(銘柄非依存または月替わりでも「今月の産地」表記が無いもの)
  - LIQUID(リキッドコーヒー、瓶入り完成品)/ COFFEE YOKAN(コーヒー羊羹、菓子)
  - コーヒー染め手袋(コーヒーで染めた手袋、雑貨)
  - 器具・グッズ(PORLEX/HARIO/Kalita/ラッセルホブス/bonmac/Welocの
    ミル・ドリッパー・サーバー・フィルター・クリーニングブラシ・クリップ等)
NON_BEAN_KEYWORDSで除外する。

【DRIP TRIPシリーズについて】
「DRIP TRIP 今月の産地「メキシコ」｜200g」のような単発購入商品(定期便ではない)
は、タイトル中に「今月の産地「国名」」の形で当月の産地が明記されており、豆の
現物販売(200g)なので対象に含める。一方「毎月ドリップバッグ25個［定期便・
月払い］」「［定期便・一括払い］」「毎月400g／200g［定期便・月払い］」は
産地非依存のサブスクリプションのため除外する(NON_BEAN_KEYWORDSの「定期便」
「定期購入」で捕捉)。

【重量について】
実データ確認済み: 東ティモール・ペルー・コスタリカ・グァテマラ・ケニア・
インドネシア・コロンビア・ブラジル・エチオピア等のストレート商品や、
逆光Blend・Takasu Blend・glove Blend等は商品名に「200g」が明記されている。
一方「IN THE MOUNTAIN」シリーズ(月替わりブレンド)や「No.3〜No.9」のナンバー
ブレンドは商品名には重量表記が無いが、バリアントが「豆／粉／Drip Bag 25p」の
3種のみで「豆」「粉」は常に同一価格(実データ確認済み、Drip Bag 25pのみ価格が
大きく異なる)であることから、この店の豆売り基準重量である200gで固定と判断
した(商品名に重量表記が無い場合はFIXED_WEIGHT_G=200を採用)。

【重量違いの重複について】
デカフェコロンビア・デカフェエチオピアは「お試し100g」と「200g」が別商品として
登録されている(バリアントではない)。基準名(末尾の重量表記を除いた部分)で
グルーピングし、最小重量を代表として採用する(BASE COFFEE南あわじ市と同じ方式)。

【代表バリアントの選定について】
各商品のバリアントは基本的に「豆／粉／(Drip Bag 25p)」の組み合わせで、豆・粉は
同一価格(実データ確認済み)。挽かない「豆」を代表バリアントとして採用し、
Drip Bag系バリアントは価格取得対象から除外する。

【flavor_notes/farm_note(テイスティングノート・農園情報)について
(2026-09-20追記)】
実データ確認済み: この店はブログ的な長文の商品説明が中心で、店舗ごとの
テーマ性が強い(自転車コラボ、登山、映画コラボ等の企画ブレンドが多数)ため、
構造化されたラベル形式のテイスティングノートは単一原産地(ストレート)
商品の一部にしかない(「国名/産地/生産地/農園/生産者/標高/精選/精製」
ラベル、<br>で区切られた1つの<p>内にまとまっている)。これはfarm_note用
フィールド(region_detail/farm_name/producer_name/altitude_note)と
processing_methodに反映する。
flavor_notesは、ラベル形式が無いブレンド商品(IN THE MOUNTAIN・No.3〜No.9等)
にも本文中に自由記述で味の説明が書かれていることが多いため、
「酸味/苦味/甘み/コク/風味/味わい/まろやか/フルーティ/チョコ/ナッツ/
キャラメル/ベリー/シトラス/フローラル/スパイシー/ボディ」等のテイスティング
記述子キーワードを含む最初の1行を採用する方式にした(店主のブログ的な
文章の中から味の説明部分だけを拾う)。当初「香り」「スッキリ」「さっぱり」も
キーワードに含めていたが、これらは自転車コラボ企画(【数量限定】「Road」
「MTB」Blend内の「山中の空気や土の香りをイメージ」)や登山記録
(IN THE MOUNTAINシリーズ内の「シャワーを借りてスッキリして」)のような
コーヒーと無関係な文脈でも頻出し、誤って抽出してしまうことが実データで
判明したため除外した(除外後も、他のキーワードと共に使われている行は
それらのキーワードで正しく抽出されるため、真陽性の取り逃しは無いことを
確認済み)。ラベルが無いブレンド商品の半数程度(Takasu Blend・逆光Blend・
Hiroshima Blend・IN THE MOUNTAINの一部等)は味の説明が本文に一切無く
(店の企画背景や個人的なストーリーのみ)、この場合は取得できないのが
正しい挙動(見送り)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method

WHITESPACE_PATTERN = re.compile(r"[ \t]+")
DESC_LABEL_PATTERN = re.compile(r"^(国名|産地|生産地|農園|生産者|標高|精選|精製)[：:]\s*(.*)$")
FARM_LABEL_TO_FIELD = {
    "国名": "region_detail",
    "産地": "region_detail",
    "生産地": "region_detail",
    "農園": "farm_name",
    "生産者": "producer_name",
    "標高": "altitude_note",
}
FLAVOR_KEYWORDS = (
    "酸味", "苦味", "苦み", "甘み", "甘さ", "コク", "風味", "味わい", "まろやか",
    "フルーティ", "チョコ", "ナッツ", "キャラメル", "カラメル", "ベリー",
    "シトラス", "フローラル", "スパイシー", "ボディ",
)


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def parse_flavor_and_farm(body_html: str | None, title: str) -> tuple[str | None, dict, str | None]:
    """理由はモジュールdocstring参照。"""
    if not body_html:
        return None, {}, None
    soup = BeautifulSoup(body_html, "html.parser")
    for tag in soup.find_all(["blockquote", "iframe", "script", "style"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")

    lines = []
    for el in soup.find_all(["p", "li", "h2", "h3", "h4"]):
        for chunk in el.get_text().split("\n"):
            line = WHITESPACE_PATTERN.sub(" ", chunk).strip()
            if line:
                lines.append(line)

    if lines and _normalize_for_compare(lines[0]) == _normalize_for_compare(title):
        lines = lines[1:]

    farm: dict = {}
    processing_raw = None
    flavor_notes = None
    for line in lines:
        m = DESC_LABEL_PATTERN.match(line)
        if m:
            label, value = m.group(1), m.group(2).strip()
            if not value:
                continue
            if label in ("精選", "精製"):
                processing_raw = value
            elif label in FARM_LABEL_TO_FIELD:
                farm[FARM_LABEL_TO_FIELD[label]] = value
            continue
        if flavor_notes is None and any(kw in line for kw in FLAVOR_KEYWORDS):
            flavor_notes = line

    return flavor_notes, farm, processing_raw

SHOP_INFO = {
    "name": "MOUNT COFFEE",
    "url": "https://mount-coffee.myshopify.com/",
    "platform": "Shopify",
    "address": "広島県広島市西区庚午北2-20-13-1F",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://mount-coffee.myshopify.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照
NON_BEAN_KEYWORDS = [
    "YAMABON", "ギフト", "ドリップバッグ", "Drip Bag", "DRIP BAG",
    "水出し用コーヒーバッグ", "定期便", "定期購入", "LIQUID", "YOKAN", "yokan",
    "コーヒー染め手袋", "セット", "PORLEX", "HARIO", "Kalita", "ラッセルホブス",
    "bonmac", "Weloc", "グラインダー", "GRINDER",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 200  # 理由はモジュールdocstring参照


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(title: str) -> bool:
    if title.startswith("『"):
        return True  # 本×コーヒーのペアリング企画(理由はモジュールdocstring参照)
    return any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS)


def normalize_base_name(title: str) -> str:
    # 末尾の「｜お試し100g」「｜200g」等の重量表記を除いた基準名でグルーピングする
    base = re.sub(r"[｜|]?\s*(お試し)?\d+\s*[gｇ]\s*$", "", title)
    return re.sub(r"\s+", " ", base).strip()


def pick_canonical_products(products: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for product in products:
        title = (product.get("title") or "").strip()
        weight_matches = WEIGHT_PATTERN.findall(title)
        weight_key = int(weight_matches[-1]) if weight_matches else FIXED_WEIGHT_G
        base = normalize_base_name(title)
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, product)
    return [product for _weight, product in by_base_name.values()]


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if (v.get("option1") or "") == "豆"]
    pool = whole_bean or [v for v in variants if "drip" not in (v.get("option1") or "").lower()]
    pool = pool or variants
    return pool[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or is_excluded(title):
        return None

    parsed = parse_product(title)
    product_url = f"https://mount-coffee.myshopify.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    weight_matches = WEIGHT_PATTERN.findall(title)
    weight_g = int(weight_matches[-1]) if weight_matches else FIXED_WEIGHT_G

    bean_powder_variants = [v for v in variants if (v.get("option1") or "") in ("豆", "粉")]
    check_variants = bean_powder_variants or variants
    all_out_of_stock = bool(check_variants) and not any(v.get("available") for v in check_variants)
    stock_status = detect_stock_status(title, all_out_of_stock)

    flavor_notes, farm, processing_raw = parse_flavor_and_farm(product.get("body_html"), title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or normalize_processing_method(processing_raw),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "farm_name": farm.get("farm_name"),
        "producer_name": farm.get("producer_name"),
        "region_detail": farm.get("region_detail"),
        "altitude_note": farm.get("altitude_note"),
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    filtered = [p for p in products if not is_excluded((p.get("title") or "").strip())]
    canonical_products = pick_canonical_products(filtered)

    records = []
    flavored_records = []
    for product in canonical_products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mountcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mountcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
