# 商品情報の掲載を一時停止している店舗(53店舗)

**店舗そのもの(名前・住所・営業時間・URL)は、掲載を続けている。止めているのは、商品情報だけ。** 登録は `scraper/products_paused.json`(`aggregate_shops.py` が、この店舗の商品を、出力に含めない)。利用者は、店舗画面の「店頭の商品を登録」で、商品を手動で登録できる。

## 1. 楽天市場・Yahoo!ショッピングの商品ページを直接取得していた店舗(39店舗)

2026-11-12。楽天市場・Yahoo!ショッピングの規約で、自動取得に事前の許可が要る(楽天のショッピングサービス利用規約に、自動化された手段での「商品ページ上の情報取得等」を禁じる趣旨の条項がある)ことが分かったため、これらの店舗の商品情報の掲載を一時停止した(`scraper/products_paused.json` に登録。`data/products.json` からも除いた。店舗は掲載を続ける)。

- 週次の自動取得に入っていたのは、2店舗(ハローコーヒー・juncoffee)だけ。ワークフローから外した。残りは、過去に手作業で実行した、単発の取得。
- 再開の条件: ①その店舗の**公式サイト**から取得できるようにする(店舗ごとに、新しいスクレイパーが要る。サイトの作りが、まちまち)、または、②公式のAPI(楽天ウェブサービス・Yahoo!ショッピングのAPI)に切り替える。再開したら、`scraper/products_paused.json` から、その店舗を消す。
- 停止した店舗数: 39 店舗 / 商品 964 件(2026-11-12時点)。

| 店舗 | 元の取得先 | スクレイパー | 公式サイト(判明分。2026-11-12のrobots・作りの簡易確認) |
|---|---|---|---|
| カフェ・ド・アミアン | Yahoo!ショッピング | scrape_amian.py | amian.co.jp |
| アンダッシュコーヒー | 楽天市場 | scrape_andushcoffee.py | gurumekan.jp(WordPress+WooCommerce) |
| 焙煎珈琲豆 楓 | Yahoo!ショッピング | scrape_baisenkaede.py | coffeekaede.com(WordPress) |
| ばいせん工房珈琲倶楽部 | 楽天市場 | scrape_baisenkobocoffeeclub.py | 未特定 |
| カフェ・アダチ | 楽天市場 | scrape_cafeadachi.py | cafe-adachi.com(BASE+WordPress) |
| カフェカンパニー | 楽天市場 | scrape_cafecompany.py | 未特定 |
| 珈々豆屋 | Yahoo!ショッピング | scrape_cocomameya.py | cocomameya.jp(WordPress+WooCommerce) |
| コーヒーシティ | Yahoo!ショッピング | scrape_coffeecity.py | 未特定 |
| 珈琲専門店 ファイブ | Yahoo!ショッピング | scrape_fivecoffeewakayama.py | 未特定 |
| フリゴレス | Yahoo!ショッピング | scrape_frigoles.py | frigoles.com(makeshop系) |
| 富久栄珈琲 | 楽天市場 | scrape_fukueicoffee.py | 未特定 |
| ハローコーヒー自家焙煎コーヒー工房 | Yahoo!ショッピング | scrape_hellocoffee.py | 未特定 |
| 広島珈琲 | Yahoo!ショッピング | scrape_hiroshimacoffee.py | 未特定 |
| 自家焙煎ひつじcoffee | Yahoo!ショッピング | scrape_hitsujicoffee.py | hitsuji-coffee.jp |
| 自家焙煎珈琲 旭川北珈館 | 楽天市場 | scrape_hokkoukan.py | 未特定 |
| 葉山 inuit coffee roaster | 楽天市場 | scrape_inuitcoffee.py | 未特定 |
| 珈琲自家焙煎工房 juncoffee | Yahoo!ショッピング | scrape_juncoffee.py | 未特定 |
| カフェ・ケストナー | 楽天市場 | scrape_kastnercoffee.py | cafe-kastner.com(接続できず) |
| 吉備の国珈琲焙煎所 | 楽天市場 | scrape_kibinokunicoffee.py | kibinokuni.a-zone-t.net(WordPress) |
| コーヒーショップ 喜蔵 | 楽天市場 | scrape_kizou.py | 未特定 |
| 珈琲工房ひぐち | 楽天市場 | scrape_kohikobohiguchi.py | cafe-higuchi.jp |
| 自家焙煎珈琲 珈嗜園 | 楽天市場 | scrape_koshiencoffee.py | 未特定 |
| 自家焙煎 珈琲豆屋 | Yahoo!ショッピング | scrape_mameyanetshop.py | 未特定 |
| 珈琲工房豆家 | Yahoo!ショッピング | scrape_mameyatajimi.py | mameya-tajimi.jp |
| 南青山珈琲 | 楽天市場 | scrape_minamiaoyamacoffee.py | organic-minamiaoyama-coffee.jp |
| なかむら珈琲 | Yahoo!ショッピング | scrape_nakamuracoffeeise.py | nakamura-coffee.jp(WordPress) |
| 京都西陣珈琲 | 楽天市場 | scrape_nishijincoffee.py | 未特定 |
| 丘の上珈琲 | 楽天市場 | scrape_okanouecoffee.py | okanoue-coffee.com |
| OK COFFEE Saga Roastery | 楽天市場 | scrape_okcoffee.py | 未特定 |
| パオコーヒー | 楽天市場 | scrape_paocoffee.py | 未特定 |
| R and R coffee labo | Yahoo!ショッピング | scrape_randrcoffeelabo.py | 未特定 |
| 高野珈琲店 | Yahoo!ショッピング | scrape_takanoniseko.py | takano-coffee.com(接続できず) |
| THE BEANS | 楽天市場 | scrape_thebeanscoffee.py | 未特定 |
| とびだす焙煎所 | Yahoo!ショッピング | scrape_tobidasubaisenjo.py | 未特定 |
| リンク珈琲 | Yahoo!ショッピング | (手動入力: scraper/m_aichi_manual_tmp.py) | linkcoffee.shop |
| 自家焙煎珈琲サイタニヤ | Yahoo!ショッピング | scrape_saitaniya.py | 未特定 |
| 小林コーヒー店 | Yahoo!ショッピング | scrape_kobayashicoffeeyamanashi.py | 未特定 |
| フレスタプラス@あらの珈琲 | Yahoo!ショッピング | scrape_frestaplus.py | 未特定 |
| 樹の香(自家焙煎珈琲豆専門店) | Yahoo!ショッピング | (手動入力: scraper/m_aichi_manual_tmp.py) | konokacoffee.com |

## 2. 店舗サイトの規約に、自動取得を禁じる記載があるため、商品情報を停止した店舗(14店舗・商品227件)

2026-11-12。規約のページに、クローリング・スクレイピングの語が禁止行為として並ぶ(Shopify標準の利用規約テンプレートとみられる文面)ため、商品情報の掲載を停止した(`scraper/products_paused.json`。`data/products.json` からも除去。店舗は掲載を続ける)。週次の自動取得に入っていた3店舗(ベルニーニ・KLATCH・round coffee)は、ワークフローから外した。利用者は、アプリの「登録した商品」で、手動で登録できる。再開するには、店舗の了承を得て、`products_paused.json` から消す。

| 店舗 | サイト |
|---|---|
| AMANO COFFEE ROASTERS | https://amano-coffee.com |
| ARCHE COFFEE | https://archecoffee.com |
| Beans. Coffee&Roasters | https://beanscoffee.jp |
| カフェ・ベルニーニ | https://caffebernini.com |
| 珈琲回廊 | https://coffeegallery.online |
| COFFEE PORT 芦屋浜ロースタリー | https://coffeeport.net |
| en. 珈琲焙煎所 | https://en-coffee.jp |
| KLATCH COFFEE | https://klatch-coffee.com |
| ミルトンコーヒーロースタリー | https://miltoncoffee.com |
| round coffee ITOSHIMA | https://round-coffee.com |
| さとやまコーヒー | https://satoyamacoffee.com |
| 岳山珈琲 | https://shop.gakuzancoffee.com |
| 焙煎工房てんぷす | https://tenpus.coffee |
| 熊本珈琲Roaster | https://www.kumamoto-coffee-roaster.store |
