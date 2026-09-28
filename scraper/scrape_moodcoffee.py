# -*- coding: utf-8 -*-
"""
scrape_moodcoffee.py

MOOD COFFEE&ESPRESSO(moodcoffee-espresso.com、茨城県水戸市南町、
Japan Coffee Roasting Championship 2024優勝・World Coffee Roasting
Championship 2025 10位の店主が営む自家焙煎スペシャルティコーヒー
ショップ)の商品情報を取得する。

【店舗発見の経緯】
全国再調査(茨城県)でmamenavi.info「茨城の自家焙煎珈琲店ガイド」から発見。

【プラットフォームについて】
実データ確認済み(2026-09時点): WordPressサイトにShopify Buy Button
(ShopifyBuy.UI)を埋め込む構成で、価格・商品説明・在庫は全てクライアント
サイドJSでShopify Storefront APIから取得しており、通常のHTML取得
(requests)では商品詳細(価格・説明文)が一切取得できない。サイトの
埋め込みJS内に公開用storefrontAccessToken(d9519b6d65d4fb57a62ad54905eb4bbc)
とShopifyドメイン(moodcoffee-espresso.myshopify.com)が明記されており、
これはShopify Buy Button埋め込みの仕組み上、ブラウザから誰でも読み取り
可能な公開トークンである(購入ウィジェットが機能するために意図的に
クライアントサイドへ公開されている)。products.jsonエンドポイントは
401だったため(myshopifyドメイン側のストア制限)、同じ公開トークンで
Storefront GraphQL APIを直接呼び出す方式を採用した。

【対象商品について】
実データ確認済み: 全18商品のうち、コーヒー豆でない商品(ドリッパー
「SIMPLIFY the Brewer」・コーヒースケール・焙煎機レンタル2種)を除いた
14銘柄(ブレンド1・ストレート13)を対象とする。

【商品説明の構造について】
実データ確認済み: descriptionHtml内に「生産地域(農園)：」「生産農園：」
「標高：」「品種：」「クロップ：」「精製方法：」「テイスト：」という
日本語ラベルと、「Region：」「Farmer：」「Process：」「Roast：」
「Flavor (Taste)：」という英語ラベルが1つの説明文に混在している。
日本語ラベルをfarm_note・flavor_notesの情報源とし、英語のRoastラベル
(Light/Medium等)のみroast_hintとして追加利用する。

【在庫状態について】
100g・豆のままバリアントのavailableForSaleフィールドで判定する
(Shopify標準の構造化在庫フラグ)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "MOOD COFFEE&ESPRESSO",
    "url": "https://moodcoffee-espresso.com/",
    "platform": "WordPress + Shopify Buy Button",
    "address": "茨城県水戸市南町2丁目4-58",
    "prefecture": "茨城県",
    "robots_txt_status": "未確認(Shopify Storefront APIの公開storefrontAccessTokenを"
                          "利用。購入ウィジェット用に意図的にクライアントサイド公開されているトークン)",
}

SHOPIFY_DOMAIN = "moodcoffee-espresso.myshopify.com"
STOREFRONT_TOKEN = "d9519b6d65d4fb57a62ad54905eb4bbc"
REQUEST_HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Storefront-Access-Token": STOREFRONT_TOKEN,
}
GRAPHQL_URL = f"https://{SHOPIFY_DOMAIN}/api/2023-01/graphql.json"

NON_BEAN_KEYWORDS = ["SIMPLIFY the Brewer", "コーヒースケール", "焙煎機利用", "Roaster利用"]

# 実データ確認済み: Shopify Buy Buttonの商品handleはWordPress側の投稿スラッグと
# 一致しないため(例: handle="chaff-blend-チャフ-ブレンド" だが実際のURLスラッグは
# "mood-blend-ムード-ブレンド")、商品ごとの実際のURLを個別に確認しハードコードした
# (2026-09時点、/category/shopping/ の一覧ページ全件のtitleタグを直接照合して確認済み)。
PRODUCT_URLS = {
    "BOLIVIA Los Rodriguez ※Tri-Up Java Kisa-in three drying / ボリビア ロスロドリゲス ※トライアップ ジャバ Kisa-in three drying":
        "https://moodcoffee-espresso.com/bolivia-los-rodriguez-%e2%80%bbtri-up-java-kisa-in-three-drying-%e3%83%9c%e3%83%aa%e3%83%93%e3%82%a2-%e3%83%ad%e3%82%b9%e3%83%ad%e3%83%89%e3%83%aa%e3%82%b2%e3%82%b9-%e2%80%bb%e3%83%88%e3%83%a9/",
    "BRAZIL GUARIROBA Black honey Lot B / ブラジル グアリロバ ブラックハニー Lot B":
        "https://moodcoffee-espresso.com/brazil-guariroba-black-honey-lot-b-%e3%83%96%e3%83%a9%e3%82%b8%e3%83%ab-%e3%82%b0%e3%82%a2%e3%83%aa%e3%83%ad%e3%83%90-%e3%83%96%e3%83%a9%e3%83%83%e3%82%af%e3%83%8f%e3%83%8b%e3%83%bc-lot-b/",
    "Brazil Ipanema Yellow Bourbon Anaerobic natural / ブラジル イパネマ イエローブルボン アナエロビックナチュラル":
        "https://moodcoffee-espresso.com/brazil-ipanema-yellow-bourbon-anaerobic-natural-%e3%83%96%e3%83%a9%e3%82%b8%e3%83%ab-%e3%82%a4%e3%83%91%e3%83%8d%e3%83%9e-%e3%82%a4%e3%82%a8%e3%83%ad%e3%83%bc%e3%83%96%e3%83%ab%e3%83%9c%e3%83%b3/",
    "CHINA Yeast fermentation honey / 中国 イーストファーメンテーションハニー":
        "https://moodcoffee-espresso.com/china-yeast-fermentation-honey-%e4%b8%ad%e5%9b%bd-%e3%82%a4%e3%83%bc%e3%82%b9%e3%83%88%e3%83%95%e3%82%a1%e3%83%bc%e3%83%a1%e3%83%b3%e3%83%86%e3%83%bc%e3%82%b7%e3%83%a7%e3%83%b3%e3%83%8f%e3%83%8b/",
    "Colombia CERRO AZUL Geisha Natural ＊CGLE / コロンビア セロアズール ゲイシャ ナチュラル ＊CGLE":
        "https://moodcoffee-espresso.com/colombia-geisha-natural-%ef%bc%8acgle-%e3%82%b3%e3%83%ad%e3%83%b3%e3%83%93%e3%82%a2-%e3%82%b2%e3%82%a4%e3%82%b7%e3%83%a3-%e3%83%8a%e3%83%81%e3%83%a5%e3%83%a9%e3%83%ab-%ef%bc%8acgle/",
    "COLOMBIA Buenos aires Geisha Washed / コロンビア ブエノスアイレス ゲイシャ ウォッシュ":
        "https://moodcoffee-espresso.com/colombia-geisha-washed-%e3%82%b3%e3%83%ad%e3%83%b3%e3%83%93%e3%82%a2-%e3%82%b2%e3%82%a4%e3%82%b7%e3%83%a3-%e3%82%a6%e3%82%a9%e3%83%83%e3%82%b7%e3%83%a5/",
    "COLOMBIA Las Flores Java Fermented Washed / コロンビア ラスフローレス ジャバ ファーメンテッドウォッシュト":
        "https://moodcoffee-espresso.com/colombia-las-flores-java-fermented-washed-%e3%82%b3%e3%83%ad%e3%83%b3%e3%83%93%e3%82%a2-%e3%83%a9%e3%82%b9%e3%83%95%e3%83%ad%e3%83%bc%e3%83%ac%e3%82%b9-%e3%82%b8%e3%83%a3%e3%83%90-%e3%83%95%e3%82%a1/",
    "ETHIOPIA Buku Saysa Anaerobic Natural / エチオピア ブクサイサ アナエロビックナチュラル":
        "https://moodcoffee-espresso.com/ethiopia-buku-saysa-anaerobic-natural-%e3%82%a8%e3%83%81%e3%82%aa%e3%83%94%e3%82%a2-%e3%83%96%e3%82%af%e3%82%b5%e3%82%a4%e3%82%b5-%e3%82%a2%e3%83%8a%e3%82%a8%e3%83%ad%e3%83%93%e3%83%83%e3%82%af/",
    "ETHIOPIA DECAF / エチオピア ディカフェ":
        "https://moodcoffee-espresso.com/ethiopia-decaf-%e3%82%a8%e3%83%81%e3%82%aa%e3%83%94%e3%82%a2-%e3%83%87%e3%82%a3%e3%82%ab%e3%83%95%e3%82%a7/",
    "ETHIOPIA Heirloom Guji G-1 Rasta Washed / エチオピア エアルーム グジ G-1 ラスタ ウォッシュト":
        "https://moodcoffee-espresso.com/ethiopia-heirloom-guji-g-1-rasta-washed-%e3%82%a8%e3%83%81%e3%82%aa%e3%83%94%e3%82%a2-%e3%82%a8%e3%82%a2%e3%83%ab%e3%83%bc%e3%83%a0-%e3%82%b0%e3%82%b8-g-1-%e3%83%a9%e3%82%b9%e3%82%bf-%e3%82%a6/",
    "ETHIOPIA WORKA SAKARO WURI NATURAL / エチオピア ウォルカサカロ ウリ ナチュラル":
        "https://moodcoffee-espresso.com/ethiopia-natural-%e3%82%a8%e3%83%81%e3%82%aa%e3%83%94%e3%82%a2-%e3%83%8a%e3%83%81%e3%83%a5%e3%83%a9%e3%83%ab/",
    "INDONESIA Wet Hulling / インドネシア ウェットハル":
        "https://moodcoffee-espresso.com/indonesia-wet-hulling-%e3%82%a4%e3%83%b3%e3%83%89%e3%83%8d%e3%82%b7%e3%82%a2-%e3%82%a6%e3%82%a7%e3%83%83%e3%83%88%e3%83%8f%e3%83%ab/",
    "KENYA KARIMIKUI AA Sl28,Sl34 Washed / ケニア カリミクイ AA Sl28,Sl34 ウォッシュト":
        "https://moodcoffee-espresso.com/kenya-karimikui-aa-sl28sl34-washed-%e3%82%b1%e3%83%8b%e3%82%a2-%e3%82%ab%e3%83%aa%e3%83%9f%e3%82%af%e3%82%a4-aa-sl28sl34-%e3%82%a6%e3%82%a9%e3%83%83%e3%82%b7%e3%83%a5%e3%83%88/",
    "MOOD BLEND / ムード ブレンド":
        "https://moodcoffee-espresso.com/mood-blend-%e3%83%a0%e3%83%bc%e3%83%89-%e3%83%96%e3%83%ac%e3%83%b3%e3%83%89/",
}

# 実データ確認済み: 商品によってラベル表記の揺れが大きく、「生産地域」「地　域」
# (文字間に全角/半角スペース)、「生産農園」「農園名」のような同義語が混在する。
# 各グループのキーごとに正規表現の代替パターンをまとめ、マッチした代替語から
# 正規化後のキーへ変換する。
LABEL_GROUPS = [
    ("生産地域", r"生産地域農園|生産地域|地\s*域"),
    ("生産農園", r"生産農園|農園名"),
    ("標高", r"標\s*高"),
    ("品種", r"品\s*種"),
    ("クロップ", r"クロップ"),
    ("精選方法", r"精製方法|精\s*製"),
    ("テイスト", r"テイスト"),
    ("Flavor", r"Flavor Taste|Flavor"),
    ("Region", r"Region"),
    ("Farmer", r"Farmer"),
    ("Process", r"Process"),
    ("Roast", r"Roast"),
]
_LABEL_ALT_TO_KEY = {}
_alt_patterns = []
for _key, _pattern in LABEL_GROUPS:
    _alt_patterns.append(f"(?P<g{len(_alt_patterns)}>{_pattern})")
    _LABEL_ALT_TO_KEY[len(_alt_patterns) - 1] = _key
LABEL_PATTERN = re.compile("(?:" + "|".join(_alt_patterns) + r")\s*[:：]\s*")


def _label_key_for_match(m: re.Match) -> str:
    for idx, key in _LABEL_ALT_TO_KEY.items():
        if m.group(f"g{idx}") is not None:
            return key
    raise AssertionError("no label group matched")

QUERY = """
{
  products(first: 50) {
    edges {
      node {
        title
        handle
        descriptionHtml
        productType
        variants(first: 20) {
          edges {
            node {
              price { amount }
              availableForSale
              selectedOptions { name value }
            }
          }
        }
      }
    }
  }
}
"""


def fetch_products() -> list[dict]:
    resp = requests.post(GRAPHQL_URL, headers=REQUEST_HEADERS, json={"query": QUERY}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [edge["node"] for edge in data["data"]["products"]["edges"]]


def build_record(node: dict) -> dict | None:
    title = (node.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    desc_html = node.get("descriptionHtml") or ""
    soup = BeautifulSoup(desc_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()
    text = re.sub(r"\n{2,}", "\n", text).strip()

    matches = list(LABEL_PATTERN.finditer(text))
    labels = {}
    for i, m in enumerate(matches):
        key = _label_key_for_match(m)
        value_start = m.end()
        value_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # 実データ確認済み: 一部商品はラベル直前に「・」箇条書き記号が付き
        # (例:「・地 域 : ...」)、次の値の直前に残ってしまうため末尾から除去する
        value = text[value_start:value_end].strip().rstrip("・").strip()
        labels.setdefault(key, value)
    intro = text[: matches[0].start()].strip() if matches else text.strip()

    price = None
    sold_out = True
    for v in node.get("variants", {}).get("edges", []):
        vn = v["node"]
        opts = {o["name"]: o["value"] for o in vn.get("selectedOptions", [])}
        if opts.get("量") == "100g" and opts.get("豆 or 粉") == "豆のまま":
            price = int(float(vn["price"]["amount"]))
            sold_out = not vn.get("availableForSale", False)
            break
    if price is None and node.get("variants", {}).get("edges"):
        vn = node["variants"]["edges"][0]["node"]
        price = int(float(vn["price"]["amount"]))
        sold_out = not vn.get("availableForSale", False)

    parsed = parse_product(title)
    normalized_title = re.sub(r"\s+", " ", title).strip()
    url = PRODUCT_URLS.get(normalized_title, "https://moodcoffee-espresso.com/category/shopping/")
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    region = labels.get("生産地域")
    if parsed["category"] != "ブレンド":
        detected = (region and detect_country_name(region)) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if region else "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産地域", "生産農園", "標高", "品種", "クロップ") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None
    flavor_notes = labels.get("テイスト") or intro or None
    roast_hint = labels.get("Roast")

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for node in fetch_products():
        detail = build_record(node)
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_moodcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_moodcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
