# -*- coding: utf-8 -*-
"""
scrape_8coffeeroast.py

8COFFEEROAST(https://www.8coffee.net/、兵庫県宝塚市安倉南1-17-14)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(兵庫県)の新規発掘で発見。

【住所について】
特定商取引法ページ(/law)の事業者所在地「〒6650823 兵庫県宝塚市安倉南1-17-14」と一致することを確認済み(2026-10)。

【対象商品について】
実データ確認済み(2026-10時点、sitemap.xml上176商品): sitemap上176商品のうち、100g入りの豆12商品を代表として収録する。同一銘柄のドリップバッグ(6〜90袋)・ディップスタイル・300g/500g/1kgの重量違い・カフェベース・Tシャツ・お試しセットは除外。例外として、ベトナム「チャムニム Red-Honey」は100gページがなく300gが、「やわらかブレンド」「ほろにがブレンド」は500gのみのためそれぞれ最小重量のページを収録した。焙煎度は説明文に明記があるものだけ設定し、他はnull。
商品名・重量・焙煎度は、商品ページ(商品名・説明文)の表記を確認したうえで下のITEMSに
明示している。価格・在庫(item_purchasability)・説明文は商品ページから実行時に取得する。
ITEMSにもEXCLUDED_IDSにも無い商品がsitemap.xmlに現れた場合は、新商品の可能性があるため
警告を表示する(自動では収録しない)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "8COFFEEROAST",
    "url": "https://www.8coffee.net/",
    "platform": "BASE",
    "address": "兵庫県宝塚市安倉南1-17-14",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.8coffee.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(商品名・説明文に明記があるものだけ。無ければNone))
ITEMS = [
    ('132568082', 'ベトナム Toiさんのロブスタ Full-Washed', 100, None, '中深煎り'),
    ('102253991', 'ベトナム Toiさんのロブスタ チャムニム Pure Natural', 100, None, None),
    ('102339653', 'ベトナム RADAR FARM Dung(ユン)さんのアラビカ カティモール アナエロビック Natural', 100, None, None),
    ('142950942', '8coffeeオリジナルブレンド やわらかブレンド', 500, None, '中煎り'),
    ('142951745', '8coffeeオリジナルブレンド ほろにがブレンド', 500, None, '中深煎り'),
    ('132977025', 'ブラジル プレミアムショコラ', 100, None, '中煎り'),
    ('101460664', 'ペルー マチュピチュ天空', 100, None, '中煎り'),
    ('102236221', 'イエメン バニーマタル アラビアンナイト アル・カマリア', 100, None, None),
    ('102065553', 'エチオピア イルガチェフェG1 チェルチェレ/ナチュラル', 100, None, None),
    ('102226042', 'タンザニア ンゴロンゴロ シャー農園 Frankさんのコーヒー Natural', 100, None, None),
    ('133084762', 'インドネシア トバブルカ スマトラマンデリンG-1', 100, None, '中深煎り'),
    ('133726636', 'ブラジル フロラータNO.2 デカフェ ノンカフェイン', 100, None, None),
    ('134894527', 'エチオピア ジマG4 ボンガフォレスト デカフェ ノンカフェイン', 100, None, '中深煎り'),
    ('133850934', 'インドネシア アチェ マンデリンG1 デカフェ ノンカフェイン', 100, None, None),
    ('102244633', 'ベトナム Toiさんのロブスタ チャムニム Red-Honey', 300, None, None),
]

# 豆以外(ドリップバッグ・セット・ギフト・定期便・器具・飲料・花・サンプル等)や、同一銘柄の
# 重複登録(重量違い・配送方法違い)のため収録しないsitemap上の商品ID
EXCLUDED_IDS = {'122096542', '132593095', '102255046', '102247542', '102340949', '132983907', '101644302', '102236784', '102066669', '102227301', '133085558', '101661879', '135447584', '101936700', '132985824', '101645038', '102238476', '102069230', '102233977', '132594293', '102257628', '102343126', '133087760', '101663705', '135452687', '101957629', '132977580', '132978097', '132978416', '101460738', '101460829', '101572815', '102236183', '102236139', '102236084', '102065489', '102065453', '101977552', '102226010', '102225975', '102225920', '132592341', '132592611', '132592849', '102253876', '102253767', '102253702', '102339368', '102339016', '102338804', '133085202', '133085314', '133085370', '101660084', '101660141', '101660200', '134894953', '134895035', '134895237', '101884656', '101884617', '101866993', '132593390', '132593557', '132593706', '132593927', '132594783', '132595251', '132595467', '102254898', '102254768', '102254685', '102254603', '101936504', '101936116', '101935926', '101935633', '133088125', '133088247', '133088354', '133085672', '133085799', '133085901', '133086008', '132986127', '132986368', '132987240', '132984252', '132984387', '132984540', '132984682', '107063304', '102342905', '102342832', '103025594', '102340913', '102342331', '102340713', '102340580', '102340398', '102257324', '102257180', '102257042', '102250642', '102250601', '102250549', '102250501', '102249848', '102247478', '102247417', '102247331', '102246867', '102244207', '102244039', '102238405', '102238376', '102238336', '102236765', '102236715', '102236683', '102236599', '102233621', '102233299', '102233175', '102227274', '102227234', '102227193', '102227154', '102069113', '102068952', '102068893', '102066638', '102066589', '102066546', '102066510', '101957367', '101957269', '101939089', '101663566', '101663458', '101663340', '101663169', '101661813', '101661759', '101661710', '101661646', '101644787', '101644679', '101644572', '101644204', '101644159', '101644116', '101644056', '135447981', '135451721', '135451783', '135451854', '135452842', '135452896', '135453070', '106651488'}

# coffee_parser.pyの国名辞書で検出できない/誤判定になる産地を明示する
ORIGIN_OVERRIDES = {}

# 説明文のうち、この文字列より後(送料・配送案内・注意書き等)はflavor_notesに含めない
DESC_CUT_MARKERS = ["＊豆のまま", "※お願い", "【送料", "-----", "北海道・沖縄へ", "【種類について】",
                    "焙煎日が限られて", "内容量", "ー・ー・", "■品名", "【賞味期限】", "※ハンドドリップ",
                    "【5,900円以上", "＊クリックポスト"]
# 説明文の先頭にある定型文(他ページへの誘導リンク・配送案内等)を取り除く正規表現
DESC_PREFIX_PATTERNS = [
    r"^(?:.*?https://www\.8coffee\.net/categories/\d+)+",
    r"^＊クリックポスト商品は400gまで同封できます。400gを超える場合はクロネコ商品をご選択ください。写真はイメージです。",
]
# 店舗全体の紹介文(商品固有の説明ではない)が入っている場合はflavor_notesにしない
DESC_GENERIC_PATTERNS = [r"自家焙煎\s*スペシャルティコーヒー.*LAKOTA", r"^Specialty coffeeのROAST"]

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one('[class*="item-detail_description"]')
    if el:
        text = el.get_text("\n")
    else:
        og = soup.select_one('meta[property="og:description"]')
        text = og.get("content", "") if og else ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    for pat in DESC_PREFIX_PATTERNS:
        text = re.sub(pat, "", text).strip()
    for pat in DESC_GENERIC_PATTERNS:
        if re.search(pat, text) and len(text) < 120:
            return None
    cut = len(text)
    for marker in DESC_CUT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            cut = min(cut, idx)
    text = text[:cut].strip()
    return text[:400] or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    desc = clean_description(soup)
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def check_new_items() -> None:
    """sitemap.xmlに未分類の商品があれば警告する(収録はしない)。"""
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] sitemap取得失敗 ({e})")
        return
    known = {item[0] for item in ITEMS} | set(EXCLUDED_IDS)
    for item_id in dict.fromkeys(re.findall(r"/items/(\d+)", resp.text)):
        if item_id not in known:
            print(f"[warn] 未分類の商品がsitemapにあります: {BASE_URL}/items/{item_id}")


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    check_new_items()
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_8coffeeroast.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_8coffeeroast.json に出力しました")


if __name__ == "__main__":
    main()
