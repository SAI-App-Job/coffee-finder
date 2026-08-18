# -*- coding: utf-8 -*-
"""
scrape_tsukikoya.py

TSUKIKOYA COFFEE ROASTER(tsukikoyacoffee.shop-pro.jp、カラーミーショップ)の
商品情報を取得する。神奈川県横須賀市追浜(追浜本店)と横浜市中区山下町
(横浜元町・中華街店)の2拠点展開。

scrape_philocoffea.pyをテンプレートに実装しているが、同じshop-pro.jpでも
このテーマはPHILOCOFFEA/Roast Design Coffee/Rhizomagいずれとも異なる
(実データ確認済み、2026-08時点)。

【文字コード】EUC-JP(実データ確認済み)。Rhizomagと同様、resp.encodingを
明示的に設定する必要がある。

【商品名の特殊な構造】
th/td形式の詳細表を持たず、商品名(var Colorme のproduct.name)自体に
「産地名- 精選方法-<br>浅煎り／中煎り／深煎り<br>(100g)<br> <br>フレーバー<br>
<br>テイスティングコメント」のように、産地・精選方法・重量・簡易フレーバー・
コメントが<br>区切りで詰め込まれている。このうち先頭セグメントを商品名として
使い、重量は"(数字g)"パターンで別途抽出する。産地国名検出(detect_country_name)
は名前全体(セグメント順不問。例:「GEISHA -Natural-<br>浅煎り<br>PANAMA...」は
3番目のセグメントに国名がある)に対して行う。

【焙煎度について】
浅煎り/中煎り/深煎りが商品ごとの固定属性ではなく、var Colorme のvariants
(option1_value)から選べる注文オプションになっている(実データ確認済み:
ほとんどの商品が3段階すべてを選択肢に持つ)。ROAST_LEVELS(8段階のカタカナ
表記)とは粒度が異なり単純な対応付けができないため、roast_levelには入れず
roast_hintとして参考保持する。選べる段階が複数ある場合のみroast_selectable=True
とする(実データ確認済み: タンザニア タリメ等、深煎りのみ販売の単一段階商品もある)。

【本文の構造化情報について】
div.p-product-body__description内に、
  - FLAVOR PROFILE: 《Aroma/香り》《Flavor/香味》《After-taste/後味》
    《Acidity/酸質》《Sweetness/甘み》《Body/ボディー》《Mouth-Feel/口触り》
  - INFORMATION: 農園：/標高：/エリア : /生産者 : /品種 : /生産処理 :
という2種類のラベル付き自由記述がある(コロンの全角/半角・前後スペース有無が
セグメントごとに異なるため、緩い正規表現で吸収する)。生産処理はここから
optimize normalize_processing_methodで正規化する(商品名からの推測より優先)。

【SCAカッピングスコア帯によるグルーピング】
var Colorme のproduct.groupsに、商品が属するグループIDのリストが入っている。
gid=2454442が「浅煎り/Specialty / 83~85points」、gid=2454443が「浅煎り/
Top Specialty / Over 85points」に対応する(実データ確認済み。「浅煎り/
UNIQUE」グループ(gid=2454441)は特殊精選のスペシャルティ豆用で、非コーヒー
豆の意味ではない)。該当グループに属する商品はSCAスコア帯をfarm_noteに追記する。

【非コーヒー豆の除外】
実データ確認済み: 「オフィシャルグッズ」(Tシャツ等)、ドリップバッグ、定期便
(現在受付停止中)、アウトドア用焙煎生豆(カフェプレ)、店舗紹介・動画チャンネル
等の非商品ページがコーヒー豆と混在する。名前ベースのキーワード除外に加え、
Roast Design Coffee等と同じ「産地国も産地情報もブレンド判定も無ければ除外」
という構造的チェックも保険として適用する(未知の非コーヒー商品への対応)。

【デカフェについて】
商品名セグメントに「デカフェ」を含む商品がある。除去方法の詳細な記載は
確認できなかったため、デカフェである旨のみdecaf_processに保持する
(存在しない除去方法を推測しない)。

【在庫について】
var Colorme のinventory_controlが"product"で、product.stock_numが構造化
されており信頼できる(Rhizomagのinventory_control:"none"とは異なる)。

robots.txt確認済み(2026年8月時点): PHILOCOFFEA等と同一の記述(User-agent: *
は/secure/と/cart/のみ制限)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "TSUKIKOYA COFFEE ROASTER",
    "url": "https://tsukikoyacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県横須賀市浦郷町3-51",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし。個人開発の反復スピード
# 優先だが、小規模個人店が多いためcourtesy設定(間隔を空けること自体)は維持する
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://tsukikoyacoffee.shop-pro.jp/"
LIST_BASE_URL = "https://tsukikoyacoffee.shop-pro.jp/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品・情報ページ
NON_BEAN_KEYWORDS = [
    "オフィシャルグッズ", "Tシャツ", "ドリップバッグ", "定期便", "カフェプレ",
    "お店のご案内", "ご挨拶", "コーヒーチャンネル",
]

# SCAカッピングスコア帯グループ(実データ確認済み)
SCA_SCORE_GROUP_LABELS = {
    2454442: "Specialty(83〜85点)",
    2454443: "Top Specialty(85点超)",
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
IMG_TAG_PATTERN = re.compile(r"<img[^>]*/?>", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"\((\d+)\s*g")
INFO_LABEL_PATTERN = re.compile(r"(農園|標高|エリア|生産者|品種|生産処理)\s*[：:]\s*([^\n]+)")
FLAVOR_LABEL_PATTERN = re.compile(r"《[^/》]+/([^》]+)》\s*([^\n]+)")

# 実データ確認済み: variantsのoption1/option2のどちらが焙煎度でどちらが挽き方かは
# 商品ごとに入れ替わる(例:複数焙煎度を選べる商品はoption1=焙煎度/option2=挽き方だが、
# 単一焙煎度のみの商品はoption1=挽き方/option2=焙煎度になっている)。スロット位置に
# 依存せず、値そのものがこの既知の焙煎度表記を含むかどうかで判定する(部分一致。
# 「浅煎り（full flover roast）」のように英語注記が付いた値も実データで確認済み
# のため、完全一致ではなく部分一致にしている)。
ROAST_TERMS = ["中深煎り", "中浅煎り", "浅煎り", "中煎り", "深煎り"]


def is_roast_value(value: str | None) -> bool:
    return bool(value) and any(term in value for term in ROAST_TERMS)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def clean_name_segments(raw_name_html: str) -> list[str]:
    """var Colorme のproduct.nameは<br>区切りの複数セグメントで構成されている
    (実データ確認済み)。この<br>は<script>内のJSON文字列値としてのリテラル
    文字列"<br>"であり、fetch_page()のDOM上のbrタグ置換(soup.find_all("br"))が
    効かない(Rhizomagのproduct.nameで判明した問題と同種)。一覧ページ側の
    <a class="c-product-list__name">はDOM要素なのでbr置換済みのテキストが
    渡ってくるが、どちらの経路でも同じ関数で正しく分割できるよう、
    実際の改行とリテラル"<br>"文字列の両方を分割対象にする。imgタグの
    直書き混入(一覧ページのalt属性起因)への保険としてIMG_TAG_PATTERNも適用する。"""
    without_img = IMG_TAG_PATTERN.sub("", raw_name_html or "")
    normalized = without_img.replace("<br>", "\n").replace("<br />", "\n").replace("\r", "")
    segments = [seg.strip() for seg in normalized.split("\n")]
    return [seg for seg in segments if seg]


def parse_description(description_html: str) -> dict:
    soup = BeautifulSoup(description_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()

    info = {label: value.strip() for label, value in INFO_LABEL_PATTERN.findall(text) if value.strip()}
    flavor_parts = [f"{label.strip()}: {value.strip()}" for label, value in FLAVOR_LABEL_PATTERN.findall(text)]

    return {"info": info, "flavor_notes": "、".join(flavor_parts) if flavor_parts else None}


def build_record(product_url: str, colorme_product: dict, description_html: str) -> dict:
    segments = clean_name_segments(colorme_product.get("name", ""))
    display_name = segments[0] if segments else ""
    full_text = " ".join(segments)

    weight_m = WEIGHT_PATTERN.search(full_text)
    weight_g = int(weight_m.group(1)) if weight_m else None
    if weight_g:
        display_name = f"{display_name} ({weight_g}g)"

    parsed = parse_product(full_text)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": display_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": colorme_product.get("sales_price_including_tax"),
            "product_url": product_url,
        }

    desc = parse_description(description_html)
    info = desc["info"]

    if info.get("生産処理"):
        parsed["processing_method"] = normalize_processing_method(info["生産処理"])
    if not parsed["origin_country"]:
        country = detect_country_name(full_text)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    non_bean_check_failed = (
        not info and not parsed.get("origin_country") and parsed.get("category") != "ブレンド"
    )
    if non_bean_check_failed:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": display_name,
            "non_bean": True,
            "product_url": product_url,
        }

    # 焙煎度: option1/option2どちらのスロットにあっても、値が既知の焙煎度表記と
    # 一致するものだけを集める(スロット位置に依存しない判定。上のROAST_TERMS参照)。
    # 選択肢が複数あれば「注文時選択」、1つのみなら固定属性として扱う。
    roast_options = sorted({
        v.get(key)
        for v in colorme_product.get("variants", [])
        for key in ("option1_value", "option2_value")
        if is_roast_value(v.get(key))
    })
    roast_hint = "／".join(roast_options) if roast_options else None
    roast_selectable = len(roast_options) > 1

    groups = colorme_product.get("groups") or []
    group_ids = {g.get("id") for g in groups if isinstance(g, dict)}
    sca_labels = [label for gid, label in SCA_SCORE_GROUP_LABELS.items() if gid in group_ids]

    farm_note_parts = []
    if info.get("農園"):
        farm_note_parts.append(f"農園: {info['農園']}")
    if info.get("エリア"):
        farm_note_parts.append(f"エリア: {info['エリア']}")
    if info.get("生産者"):
        farm_note_parts.append(f"生産者: {info['生産者']}")
    if info.get("標高"):
        farm_note_parts.append(f"標高: {info['標高']}")
    if info.get("品種"):
        farm_note_parts.append(f"品種: {info['品種']}")
    if sca_labels:
        farm_note_parts.append(f"SCAカッピングスコア: {'/'.join(sca_labels)}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    decaf_process = "デカフェ(除去方法の詳細記載なし)" if "デカフェ" in full_text else None

    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(display_name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 3段階(浅煎り/中煎り/深煎り)でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": roast_hint,
        "roast_selectable": roast_selectable,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": desc["flavor_notes"],
        "blend_components": [],
        "decaf_process": decaf_process,
        "price": colorme_product.get("sales_price_including_tax"),
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    body_el = soup.select_one("div.p-product-body__description")
    description_html = body_el.decode_contents() if body_el else ""

    return build_record(url, colorme_product, description_html)


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.c-product-list__item")

    results = []
    for item in items:
        name_link_el = item.select_one("a.c-product-list__name")
        price_el = item.select_one("div.c-product-list__price")
        if not name_link_el:
            continue

        segments = clean_name_segments(name_link_el.get_text())
        display_name = segments[0] if segments else ""
        if any(kw in " ".join(segments) for kw in NON_BEAN_KEYWORDS):
            continue

        href = name_link_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)円", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_status = detect_stock_status(display_name)

        results.append({
            "raw_name": display_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = []
    page = 1
    while True:
        items = scrape_product_list_page(page)
        if not items:
            break
        all_list_items.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_tsukikoya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_tsukikoya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
