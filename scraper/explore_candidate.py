# -*- coding: utf-8 -*-
"""
explore_candidate.py

新しいスクレイピング候補サイトを渡すと、以下を自動的に調べて報告する:
  1. robots.txtの状況(全面禁止/一部制限/全面許可)
  2. ページのHTMLから、既知のECプラットフォームの「指紋」を検出
  3. 検出結果に基づき、scraper/ 内の既存スクレイパーのうちどれが
     テンプレートとして最も近いかを提案

【狙い】これまでの4サイト(Denim bis / MiLL Coffee / PHILOCOFFEA / SCAJ / WCC)
調査で、robots.txt確認とブラウザでのHTML構造確認が毎回人手の作業になっていた。
このスクリプトはその「探索フェーズ」をClaude Code側で完結させ、人手を介さずに
候補サイトの下調べを済ませることを目的とする。

使い方:
    python explore_candidate.py https://example-coffee-shop.com/

出力:
    - コンソールに調査結果のサマリー
    - candidates/<ドメイン名>.html にページのHTML(構造確認用に保存)
"""

import re
import sys
import urllib.parse
from pathlib import Path

import requests

CRAWL_DELAY_SECONDS = 10
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# ---------------------------------------------------------------------------
# プラットフォームの指紋(fingerprint)定義
# これまで実装した scraper/ 内のスクレイパーが対応済みのプラットフォームを
# 中心に、日本の個人店でよく使われる主要プラットフォームも追加している。
# 判定方法: HTMLソース中に特徴的な文字列が含まれるかを正規表現でチェック。
# ---------------------------------------------------------------------------
PLATFORM_FINGERPRINTS = [
    {
        "platform": "Ocnk(おちゃのこネット)",
        "patterns": [r"ocnk", r"class=\"item_data\"", r"list_item_cell"],
        "similar_scraper": "scrape_denimbis.py",
        "note": "一覧はli.list_item_cell、詳細ページに商品説明の構造化記述があるパターン。",
    },
    {
        "platform": "Wix",
        "patterns": [r"data-hook=", r"wix-warmup-data", r"static\.wixstatic\.com"],
        "similar_scraper": "scrape_millcoffee.py",
        "note": "data-hook属性ベースでの抽出が有効。キー=値形式の説明文が多い。",
    },
    {
        "platform": "カラーミーショップ",
        "patterns": [r"shop-pro\.jp", r"colorme", r"class=\"productList__"],
        "similar_scraper": "scrape_philocoffea.py",
        "note": "th/td形式の詳細表(BEANS DATA相当)が使われていることが多い。汎用キーバリュー抽出が有効。",
    },
    {
        "platform": "ShopServe(ショップサーブ)",
        "patterns": [r"shopserve\.jp", r'affiliation:\s*"shopserve"', r'class="sps-'],
        "similar_scraper": "scrape_mui.py",
        "note": "実データ確認済み(Mui、2026-08時点)。robots.txtが存在しない店舗もある"
                "(404=実質全面許可)。商品詳細ページに`gtag('event', 'view_item', {...})`が"
                "埋め込まれており、非クォートのJS object literalだが税込価格(price)と"
                "カテゴリタグ(item_category、産地・焙煎度・ブレンド/シングルオリジン区分を含む)を"
                "正規表現で直接抜き出せる。単一原産地の商品のみtable.info-table"
                "(国名/地域/生産者/精製工場/オーナー/標高/品種/精製のth/td形式)を持ち、"
                "ブレンド商品には存在しない。商品一覧のページ送りは"
                "/SHOP/<カテゴリID>/t02/list<N>.html というURLでGETアクセス可能。",
    },
    {
        "platform": "Webflow",
        "patterns": [r"webflow\.js", r"data-wf-", r"w-webflow-badge"],
        "similar_scraper": "scrape_events_scaj.py",
        "note": "比較的クリーンなセマンティックHTML。div+見出しの繰り返しパターンが多い。",
    },
    {
        "platform": "Squarespace",
        "patterns": [r"squarespace-cdn\.com", r"sqs-block", r"static\.squarespace\.com"],
        "similar_scraper": "scrape_events_wcc.py",
        "note": "Fluid Engineはブロックのクラス名がハッシュ値で不安定。CSS構造よりテキストパターンでの正規表現抽出を推奨。",
    },
    {
        "platform": "crayon(クレヨン)",
        "patterns": [r"crayonsite\.net", r"crayon\.e-shops\.jp", r"crayonimg\.e-shops\.jp", r"powered by crayon"],
        "similar_scraper": "scrape_rakuen.py",
        "note": "個別商品ページを持たず、1つの一覧ページの<p>タグ内に<br>区切りで商品名・価格が"
                "自由記述で埋め込まれるパターンが確認されている(楽園)。価格の全角/半角表記ゆれに注意。",
    },
    {
        "platform": "Tsuku2(ツクツク)",
        "patterns": [r"ec\.tsuku2\.jp", r"tsuku2\.jp/shop", r"api-internal/item-ranking"],
        "similar_scraper": None,
        "note": "未対応(実データ確認済み、2026-08時点)。robots.txtはUser-agent:*にDisallow:なし"
                "(全面許可)だが、ドメイン全体がAkamai Bot Manager配下にあり、requests/WebFetch等の"
                "非ブラウザクライアントはTLSハンドシェイク段階でスタール・切断される(robots.txt自体も"
                "取得不可なほど厳格)。実ブラウザ(このリポジトリのbrowserツール等)経由でのみ閲覧・"
                "調査ができ、GitHub Actions上のPython requestsでは同様にブロックされる可能性が高い。"
                "商品グリッド自体はサーバー側で描画済み(在庫状態のみ/api-internal/item-stock-with-child"
                "で後から取得)なので、Akamaiさえ突破できればHTML構造の解析自体は難しくない。",
    },
    {
        "platform": "Shopify",
        "patterns": [r"cdn\.shopify\.com", r"Shopify\.theme", r"shopify-section"],
        "similar_scraper": None,
        "note": "未対応。Shopify標準のproducts.json APIが公開されている場合、スクレイピングより先にそちらを確認する価値がある。",
    },
    {
        "platform": "BASE",
        "patterns": [r"thebase\.in", r"base-ec2", r"cdn\.thebase\.in", r"theshop\.jp"],
        "similar_scraper": "scrape_cafeclaudia.py",
        "note": "対応済み。カテゴリページ(?page=N)から商品URLを収集し、詳細ページの"
        "h1.itemTitle/#price/挽き方セレクトのdata-stockを見る構成(カフェクラウディア調査時)。"
        "【重要】BASEの白ラベルサービスであるtheshop.jpサブドメインの店舗は、実データ調査の結果"
        "テーマによって構造が大きく異なることが判明している(2026-08時点)。NAGI COFFEE/"
        "FINETIME COFFEE ROASTERS/WOODBERRY COFFEEは商品詳細ページにschema.org JSON-LD"
        "(<script type=\"application/ld+json\">)が埋め込まれるテーマで、name/description/"
        "offers.price/offers.availabilityを構造化データとして取得できる(scrape_nagi.py/"
        "scrape_finetime.py参照)。一方chouette torréfacteur laboratoireは「Relation」という"
        "別テーマで、JSON-LDが一切無く、商品説明文(itemDescription)も全商品共通の定型文の"
        "みで個別情報を含まない。この場合はh1.itemTitle(商品名)・div#price内のp(価格)・"
        "div.stockStatus(hasStockクラスの有無で在庫判定)という素のHTML要素から取得し、"
        "産地・精選方法・焙煎度等はすべて商品名のみをcoffee_parser.parse_product()で解析する"
        "しかない(scrape_chouette.py参照)。新規のtheshop.jp店舗を調査する際は、まず商品詳細"
        "ページにJSON-LDがあるかどうかを最初に確認し、無ければscrape_chouette.pyを、あれば"
        "scrape_nagi.py/scrape_finetime.pyをテンプレートにする。",
    },
    {
        "platform": "STORES",
        "patterns": [r"stores\.jp", r"stores-fs"],
        "similar_scraper": "scrape_yoshida.py",
        "note": "参考実装あり(吉田珈琲焙煎所、2026-08時点)が、GitHub Actions上での"
                "自動実行には現状未対応。ロジック自体はscrape_yoshida.pyとしてローカルで"
                "動作検証済み(/itemsページのa.c-itemList__item-linkから一覧取得、"
                "詳細ページはh1.item_name・ng-init内のdetailCtrl.salesPrice=N・"
                "div.main_content_result_item_list_detail[ng-non-bindable、実テキストの"
                "\\nで構造化ラベル(原産国：/焙煎度：等)を含む]で取得可能)。ただし"
                "GitHub Actionsランナーからのリクエストは、識別可能なUser-Agentや"
                "ブラウザ相当のAccept系ヘッダーを付けてもCloudflareに一貫してHTTP 403"
                "Forbiddenでブロックされる(ローカル環境の同一UAでは200)。IPレピュテーション"
                "によるものと推定され、Tsuku2(Akamai)と同種の問題。デフォルトのcurl"
                "(UA無し)だとローカルからでもCaptcha Challenge(403)になる点にも注意"
                "(識別可能なUser-Agent自体は必須)。robots.txtはUser-agent: *に対し"
                "/cart・/checkout・/login・/mypage・/search・/tokushoho等の非公開/取引系"
                "のみDisallowで、Crawl-delay: 20が明示されている。",
    },
    {
        "platform": "WordPress + WooCommerce",
        "patterns": [r"wp-content", r"woocommerce"],
        "similar_scraper": None,
        "note": "未対応。ただしWordPress系はプラグイン差異が大きく、店舗ごとの個別調査が必要になりやすい。",
    },
    {
        "platform": "Goope(グーペ)",
        "patterns": [r"r\.goope\.jp", r"cdn\.goope\.jp", r"goope"],
        "similar_scraper": "scrape_kagisippo.py",
        "note": "対応済み(かぎしっぽ、2026-08時点)。ECカート機能を持たず、/menu配下の"
                "「メニュー表」ページに商品名・価格・説明文をテキストで掲載する形式"
                "(var Colorme・products.json・JSON-LD等の構造化データは一切無い)。"
                "商品説明はdiv.textfield内の複数の<p>タグに分かれており、1段落に複数の"
                "「ラベル：値」が詰め込まれていることがあるため、段落ごとに独立して"
                "ラベルを抽出する必要がある(段落を跨いで抽出すると、末尾にラベルを"
                "持たない自由記述段落が直前のラベルの値に混入する不具合が実データで"
                "判明した)。ルートのrobots.txtはgoope.jpのマーケティングサイトへ"
                "302リダイレクトされ実体が存在しない(404と同じく全面許可とみなせる)。",
    },
]


def check_robots_txt(base_url: str) -> dict:
    """理由: requestsのデフォルト(allow_redirects=True)のままだと、robots.txt自体が
    存在せずトップページ等の無関係なコンテンツへリダイレクトされるサイト(Goope等、
    2026-08時点でkagisippo-coffeeで確認済み)で、そのリダイレクト先のHTMLを
    robots.txtの本文として誤って解析してしまう。リダイレクトを自動追従せず、
    リダイレクト先のパスが引き続き/robots.txtを指す場合(スキーム統一等)のみ
    追従し、それ以外(トップページ等の無関係な場所への転送)は「robots.txtなし」
    として扱う。"""
    robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
    url_to_fetch = robots_url
    resp = None
    for _ in range(5):  # リダイレクトチェーンの上限(通常のscheme統一等を想定)
        try:
            resp = requests.get(url_to_fetch, headers=REQUEST_HEADERS, timeout=10, allow_redirects=False)
        except requests.RequestException as e:
            return {"status": "取得失敗", "detail": str(e), "url": robots_url}

        if resp.status_code not in (301, 302, 303, 307, 308):
            break
        location = resp.headers.get("Location")
        if not location:
            break
        next_url = urllib.parse.urljoin(url_to_fetch, location)
        if urllib.parse.urlparse(next_url).path.rstrip("/") != "/robots.txt":
            # robots.txt以外の場所(トップページ等)へ転送された = 実体が無いのと同義
            return {
                "status": "robots.txtなし(全面許可とみなせる。robots.txtへのリクエストが"
                          f"{next_url} へリダイレクトされ、robots.txt自体が実在しない)",
                "detail": None,
                "url": robots_url,
            }
        url_to_fetch = next_url

    if resp is None:
        return {"status": "取得失敗", "detail": None, "url": robots_url}
    if resp.status_code == 404:
        return {"status": "robots.txtなし(全面許可とみなせる)", "detail": None, "url": robots_url}
    if resp.status_code != 200:
        return {"status": f"取得失敗(HTTP {resp.status_code})", "detail": None, "url": robots_url}

    text = resp.text
    # User-agent: * ブロック内のDisallowを大まかに拾う(厳密なパーサーではなく、
    # 「全面禁止/一部制限/ほぼ許可」を素早く判定するための簡易チェック)
    star_block_match = re.search(
        r"User-agent:\s*\*\s*(.*?)(?=\nUser-agent:|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    disallow_lines = []
    if star_block_match:
        disallow_lines = re.findall(r"Disallow:\s*(\S*)", star_block_match.group(1))

    root_disallowed = any(line.strip() == "/" for line in disallow_lines)
    if root_disallowed:
        status = "全面禁止(User-agent: * に Disallow: / )"
    elif disallow_lines and any(d.strip() for d in disallow_lines):
        status = f"一部制限あり(Disallow: {', '.join(d for d in disallow_lines if d.strip())})"
    else:
        status = "実質許可(一般コンテンツへの制限なし)"

    return {"status": status, "detail": text[:2000], "url": robots_url}


def detect_platform(html: str) -> list[dict]:
    matched = []
    for fp in PLATFORM_FINGERPRINTS:
        hit_count = sum(1 for pattern in fp["patterns"] if re.search(pattern, html, re.IGNORECASE))
        if hit_count > 0:
            matched.append({**fp, "hit_count": hit_count, "hit_total": len(fp["patterns"])})
    matched.sort(key=lambda m: m["hit_count"], reverse=True)
    return matched


def explore(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.replace(":", "_")
    base_url = f"{parsed.scheme}://{parsed.netloc}/"

    print(f"=== 探索対象: {url} ===\n")

    # 1. robots.txt確認
    robots_result = check_robots_txt(base_url)
    print(f"[robots.txt] {robots_result['status']}")
    print(f"  確認URL: {robots_result['url']}\n")

    if "全面禁止" in robots_result["status"]:
        print("robots.txtで全面禁止されているため、以降の調査を中止します。")
        return

    # 2. ページ取得とプラットフォーム判定
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ページ取得] 失敗: {e}")
        return

    html = resp.text
    matches = detect_platform(html)

    if matches:
        print("[プラットフォーム判定] 検出結果(一致度が高い順):")
        for m in matches[:3]:
            print(f"  - {m['platform']}(一致 {m['hit_count']}/{m['hit_total']})")
            if m["similar_scraper"]:
                print(f"    → 参考にできる既存スクレイパー: scraper/{m['similar_scraper']}")
            print(f"    → {m['note']}")
    else:
        print("[プラットフォーム判定] 既知のプラットフォームには一致しませんでした。独自CMSの可能性があります。")

    # 3. HTMLを保存(構造確認用)
    candidates_dir = Path("candidates")
    candidates_dir.mkdir(exist_ok=True)
    out_path = candidates_dir / f"{domain}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\n[保存] ページのHTMLを {out_path} に保存しました(構造確認用)。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python explore_candidate.py <URL>")
        sys.exit(1)
    explore(sys.argv[1])
