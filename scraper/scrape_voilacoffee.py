# -*- coding: utf-8 -*-
"""
scrape_voilacoffee.py

ヴォアラ珈琲(VOILA COFFEE、www.umaicoffee.jp、〒899-4332 鹿児島県霧島市
国分中央5-3-17、自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃの
こネット(Ocnk、umaicoffee.jpは独自ドメイン)。

【ドメインとプラットフォームについて】
実データ確認済み(2026-09時点): 候補リストでは「独自(custom)」と推定されて
いたが、robots.txtの記述(GPTBot/Bytespider/TikTokSpider/meta-external
agentのみDisallow: /)・HTML内の"ocnk"文字列・特定商取引法ページのURL
パターン(/info)・商品ページのURLパターン(/product/N)がいずれも他のOcnk
店舗と一致し、実際はOcnk(独自ドメイン)であることを確認した。
umaicoffee.jp(wwwなし)は301でwww.umaicoffee.jpにリダイレクトされるため、
本スクレイパーは全リクエストをwwwありのURLに送信する。

robots.txt確認済み(2026-09時点): 他のOcnk店舗と同一の記述。User-agent: *
には制限なし。

【住所について】
特定商取引法ページ(https://www.umaicoffee.jp/info)で実データ確認済み
(2026-09時点): 「所在地」欄に「〒899-4332 鹿児島県霧島市国分中央５丁目
３番17号」(全角表記)との記載を確認。候補リストの住所(5-3-17)と一致。

【商品情報の取得方法について】
実データ確認済み: sitemap.xmlの/product/N配下に全135件あるが、大半(120件)
は器具・フィルター・ドリップバッグ・水出しコーヒー・ギフトセット・
Tシャツ等の非対象商品で、これらは商品ページのproduct:price:amountメタ
タグに固定価格が入っている。一方、単一銘柄のコーヒー豆(15件)は「豆のまま
/中挽き」の挽き方と「250g/1kg」等の重量の2軸バリエーション制のため、
メタタグに価格が入らない(価格は商品ページ本文の構造化テーブル
class="variation_label"内に「250g 1,900円」のような文字列で埋め込まれて
いる)。本スクレイパーはメタタグに価格が無い商品のうち、本文に
「【生産国】」という産地表示の構造化ラベルを含むものだけを対象とする
ことで、価格タグの無いTシャツ(3件、VOILA Tシャツ 2024/2025/2026)を
自然に除外する(構造化産地ラベルを持たないため)。

【産地・精選方法の取得について】
実データ確認済み: 対象15件はいずれも商品名だけでは産地が特定できない
場合が多い(例:「モカ・クラシック」の実際の産地はエチオピア、
「アニバーサリー」はニカラグア)。商品ページ本文に「【生産国】エチオピア
／Ethiopia」「【生産処理方法】ウォッシュド／Washed」のような構造化ラベルが
必ず記載されているため、商品名パース(parse_product)で産地・精選方法が
検出できなかった場合にこの構造化ラベルからフォールバック抽出する
(Denim bis等の説明文パースと同じ発想だが、ラベル書式がこの店舗独自の
形式なため本ファイル内で専用の正規表現を実装している)。全15件とも単一産地
(ブレンドは無い)。

【重量違いについて】
実データ確認済み: 全15件が「250g」を基本重量として持つ(1件のみ250gの
みでバリエーションが無い)。価格は250g(最小重量)のものを採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 商品ページのdiv.item_descに「【風味の特徴と印象】」
という見出しがあり、直後に短いテイスティング文が続く(対象15件中14件で
確認)。見出し以降、「この豆の味わい」(焙煎度・酸味・コクのスライダー
UIラベル)が始まる直前までを採用する。1件は同見出し自体が存在せず、
店舗側でテイスティング文が用意されていないgenuineな欠落と判断した。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "ヴォアラ珈琲",
    "url": "https://www.umaicoffee.jp/",
    "platform": "おちゃのこネット",
    "address": "鹿児島県霧島市国分中央5-3-17",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。他のOcnk店舗と同一の記述。"
                          "User-agent: *には制限なし)",
}

BASE_URL = "https://www.umaicoffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

ORIGIN_LABEL_PATTERN = re.compile(r"【生産国】\s*([^/／\n]+)")
PROCESSING_LABEL_PATTERN = re.compile(r"【生産処理方法】\s*([^/／\s<]+)")
VARIATION_WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)[\s　]*([\d,]+)円")
FLAVOR_PATTERN = re.compile(r"【風味の特徴と印象】\s*(.*?)(?=この豆の味わい|\Z)", re.DOTALL)


def extract_flavor_notes(html: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one("div.item_desc")
    if not desc_el:
        return None
    for br in desc_el.find_all("br"):
        br.replace_with("\n")
    text = desc_el.get_text("\n", strip=True)
    m = FLAVOR_PATTERN.search(text)
    result = m.group(1).strip() if m else None
    return result or None


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def pick_min_weight_variation(html: str) -> tuple[int, int] | None:
    """商品説明本文のバリエーション表から(重量g, 価格)の最小重量ペアを返す。"""
    candidates = []
    for m in VARIATION_WEIGHT_PATTERN.finditer(html):
        num, unit, price_str = m.group(1), m.group(2), m.group(3)
        weight_g = int(num) * 1000 if unit == "kg" else int(num)
        price = int(price_str.replace(",", ""))
        candidates.append((weight_g, price))
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[0])


def build_record(title: str, html: str, product_url: str) -> dict | None:
    parsed = parse_product(title)

    # 実データ確認済み(2026-09時点): 「シティオ・ダ・トーレ農園」(ブラジルの
    # 農園名、ポルトガル語Sítio=農地)はcoffee_parser.pyのROAST_KEYWORDS
    # 「シティ」が「シティオ」の部分文字列に誤爆し、実際には言及の無い
    # 「シティロースト」が焙煎度として誤検出される。地名・農園名由来の
    # 誤検出のみをこの店舗のスクレイパー内でローカルに補正する
    # (coffee_parser.py共通ロジックの変更は本タスクの範囲外のため)。
    if parsed["roast_level"] == "シティロースト" and "シティオ" in title and "シティロースト" not in title:
        parsed["roast_level"] = None

    if parsed["is_flavored"]:
        weight_price = pick_min_weight_variation(html)
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": weight_price[1] if weight_price else None,
            "product_url": product_url,
        }

    # 商品名パースで産地・精選方法が取れなければ、本文の構造化ラベルから補完する
    # (理由はモジュールdocstring参照)
    if not parsed["origin_country"]:
        m = ORIGIN_LABEL_PATTERN.search(html)
        if m:
            country = detect_country_name(m.group(1).strip())
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description"

    if not parsed["processing_method"]:
        m = PROCESSING_LABEL_PATTERN.search(html)
        if m:
            parsed["processing_method"] = normalize_processing_method(m.group(1).strip())

    weight_price = pick_min_weight_variation(html)
    if not weight_price:
        return None
    weight_g, price = weight_price

    stock_status = detect_stock_status(title)

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
        "flavor_notes": extract_flavor_notes(html),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            html = fetch_html(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if not title_m:
            continue
        title = title_m.group(1).split(" | ")[0].strip()

        price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', html)
        if price_m and price_m.group(1):
            # メタタグに固定価格がある商品は器具・ドリップバッグ・ギフト等の
            # 非対象商品(理由はモジュールdocstring参照)。
            continue

        if "【生産国】" not in html:
            # コーヒー豆以外の価格非公開商品(Tシャツ等)を除外する
            continue

        detail = build_record(title, html, product_url)
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
    with open("data_voilacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_voilacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
