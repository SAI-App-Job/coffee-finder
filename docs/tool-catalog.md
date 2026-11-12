# 器具カタログ(data/tools.json)

設定「マイツール」の追加画面で、ドリッパー・サイフォン・フレンチプレス・エアロプレス・コーヒーメーカー・ペーパー・コーヒーミルを、名前の一部やJAN(GTIN)から選んで登録するための、メーカー公式の情報のカタログ。
アプリは、追加画面を開いたときに、GitHub上の `data/tools.json` を1回だけ取得する(商品データと同じ配り方)。取得できなければ、候補が出ないだけで、手入力の登録はできる。

## 方針
- 値は、**メーカー公式のサイト**から取る(販売店・まとめサイトは使わない)。取れなかった項目は、空にする(推測しない)。
- 取得した原文は、`source-archive/tools-<メーカー>-<日付>/` に保存する(git管理外。非公開のバックアップ用リポジトリに入れる)。
- **価格は載せない**(変わりやすい)。**画像も載せない**(著作権)。
- JAN(GTIN)は、桁数とチェックデジットを検査し、合わないものは載せない。
- **古い情報は、消さない**(2026-11-12〜)。公式サイトで新製品が出て、古い器具のページが消えても、利用者は、古い器具を持っている。取得し直したとき、今回の取得に載っていない項目・型番は、**消さずに残し**、印を付ける。
  - 項目: `status: "notListed"`、`notListedSince`(載っていないと最初に気づいた日)。型番だけが載らなくなったときは、その型番に `notListedSince`。
  - `checkedAt`(最後に公式サイトで確認した日)と `sourceId`(その時の原文)は、そのまま。また載れば、印は自動で消える。
  - 対象は、同じ取得元(`sourceId` が `tools-<取得元>-<日付>`)の項目だけ。他の取得元の項目・他のメーカーは、触らない。
  - 取得が0件のときは、サイトの不具合とみなして、何も変えない。
  - 画面の登録の候補には、現行のものを先に出し、印のあるものには「公式サイトに、現在載っていません(日付に確認)」と出す(選べる)。
  - `npm run tools:check` は、印の形式を検査し、残している件数を出す。
  - `--reuse`(保存した原文から作り直す)は、サイトを確認していないため、`checkedAt` を、原文を取った日にする。
- 更新は手動で、定期的に行う。器具の新製品は、商品(豆)より少ないため、年に数回で足りる。

## 作り方・更新
```bash
python -X utf8 scripts/build_tools_catalog.py hario            # hario.com から取得して、data/tools.json に反映(同じメーカーの項目は入れ替わる)
python -X utf8 scripts/build_tools_catalog.py kalita           # Kalita
python -X utf8 scripts/build_tools_catalog.py kalita --reuse   # 取得済みの原文から作り直す(サイトにはアクセスしない)
npm run tools:check                                            # 検査
```

### 公式ショップ(Shopify)から、JANを取る
HARIO・TIMEMORE・Fellow・ORIGAMIの公式オンラインショップは、Shopifyで作られている。各商品の `/products/<ハンドル>.js` に、型番(sku)ごとのJAN(`barcode`)がある。
**取得の間隔が短いと取得制限(429)がかかる。作業用の端末では取得できなかったため、利用者のPCで実行する。**
```bash
python -X utf8 scripts/build_tools_catalog.py hario-shop --dry-run   # まず、対象になる商品の一覧だけを確認(一覧の取得のみ)
python -X utf8 scripts/build_tools_catalog.py hario-shop             # HARIO: 既存の項目に、JANを型番(sku)で補う。既存に無い型番の製品は、追加する
python -X utf8 scripts/build_tools_catalog.py timemore               # TIMEMORE(同じメーカーの項目は入れ替わる)
python -X utf8 scripts/build_tools_catalog.py fellow
python -X utf8 scripts/build_tools_catalog.py origami
npm run tools:check
```
- 取得の間隔は2秒。一覧は、全ページ(250件ずつ)取る(HARIOは、「coffee」の一覧だけ)。
- **取得制限(429)が続くとき**: 数十分〜数時間、間隔を空けてから、やり直す。それでも取れないときは、次の「ブラウザで書き出す方法」を使う。
- 種類(ドリッパー・ペーパー・ミル)は、商品名から決める。`--dry-run` で一覧を見て、載せたくないものが入っていれば、`shopify_kind_en` / `hario_kind` の除外の語を足す。
- JANは、桁数とチェックデジットが合うものだけ載せる(合わないものは、警告を出して、空にする)。店が入力した値のため、メーカーの公式の値と違う場合がありうる。
- 取得した原文は、`source-archive/tools-<名前>-<日付>/` に保存される。


取得の間隔は6秒(公式サイトへの負荷と、取得制限を避けるため)。

### ブラウザで書き出す方法(取得制限がかかりやすいとき)
ふつうの閲覧と同じ見え方で取得するため、取得制限がかかりにくい。
1. ブラウザで、公式ショップのトップページを開く(例: https://shop.hariocorp.co.jp/)。**そのサイトの上で実行する**
2. PowerShellで、スクリプトを、クリップボードにコピーする: `Get-Content scripts\shopify-export.js -Raw -Encoding UTF8 | Set-Clipboard`(**`-Encoding UTF8` が必要**。無いと、日本語が文字化けして、貼り付けたコードが動かない)
3. ブラウザで F12 を押して、開発者ツールの「コンソール」を開き、貼り付けて Enter(「貼り付けを許可」と入力するよう求められたら、入力する)
4. 数分後に、`tools-<メーカー>.json` が、自動でダウンロードされる(進み具合は、コンソールに出る)
5. そのファイルを、プロジェクトのフォルダに置いて、実行する:
```bash
py -X utf8 scripts/build_tools_catalog.py hario-shop --from-file tools-hario-shop.json --dry-run   # 対象の一覧を確認
py -X utf8 scripts/build_tools_catalog.py hario-shop --from-file tools-hario-shop.json             # 反映
```
種類の判定と除外は、Python側で行う(ブラウザ側の絞り込みは、取りこぼさないための、ゆるいもの)。

## 項目
`items[]`: `id`・`kind`(dripper / paper / grinder)・`maker`・`makerAlias`(検索用の読み)・`name`・`variants[]`(`label`色・大きさ、`sku`品番、`gtin`)・`url`(公式の製品ページ)・`checkedAt`・`sourceId`(原文の資料ID)。
- `sourceType`: 情報の出どころの種類。`"official"`(メーカーの公式サイト・公式ショップ)か、`"retailer"`(販売店のページ。現在は Comandante・AeroPress・TIMEMOREの一部)。**`retailer` の項目は、マイツールの登録で、商品ページのURLを入れない**(公式ページではないため。`src/utils/toolCatalog.js`)。新しく販売店から取り込むときは、`RETAILER_MAKERS` / `RETAILER_ID_PREFIXES`(`scripts/build_tools_catalog.py`)に足す。
- `power`: 電動の印(`"electric"`)。**根拠がある場合だけ**付ける(商品名に「電動」「electric」「automatic」がある、Kalitaの公式の「電動ミル」の一覧にある、電動だけを扱うシリーズ・メーカー、ボダムの「Electric Coffee Grinders」)。印が無いものは、「手挽き」ではなく、「不明」。

## 収録の状況(2026-11-10)
| メーカー | 件数 | JAN | 取得元 | メモ |
|---|---|---|---|---|
| Kalita | 115製品 | 115 | 公式サイトの製品ページ(kalita.co.jp) | 製品ページの題名は型番だけのものが多いため、種類の名前(ドリッパー等)を前に付けた。ネルフィルター・セット・ポット等は除外 |
| HARIO | 97製品(124型番) | 119 | 名前・型番は公式サイト(hario.com)、JANは公式オンラインショップ(shop.hariocorp.co.jp。ブラウザで書き出し) | ショップの商品で、hario.comに無いもの(コラボ品・限定品など19製品)も追加。JANが無い5型番は、ショップに無い(ALPHA DRIPPER TRITAN・SHIZUKA・コーヒーミル ウォールナット・マイカフェドリップフィルター)か、ショップの値が空(V60ペーパーフィルターM 50枚フック穴あり)。hario.comとショップで型番の書き方が違う1件(SUIREN ブラック＆ホワイト)は、別名の表(`HARIO_SKU_ALIAS`)で対応 |
| Melitta | 22製品(26型番) | 26 | 公式サイトの製品ページ(melitta.co.jp。家庭用のハンドドリップ器具・フィルターペーパー・ミル) | ページの「スペック」の表(型番・JAN)から。ケトル・サーバーは除外。メリタでは、ドリッパーを「コーヒーフィルター」「アロマフィルター」と呼ぶ。業務用は未収録 |
| 1Zpresso | 11機種 | 0 | 公式サイト(1zpresso.coffee) | 公式サイトに、型番・JANの表が無い。機種名は、各シリーズのページの見出しにあるものだけ(スクリプトが、ページにその文言があることを確かめてから載せる)。Q・X・ZP6の個別の機種名は、公式ページの見出しに無いため未収録 |
| TIMEMORE | 17製品(36型番) | 28 | 公式オンラインショップ(www.timemore.com。ブラウザで書き出し) | 公式の英語サイトのため、JANは、中国のGS1の番号(6959…)で、日本の店で売る品のJANと違う場合がありうる。JANが空の8型番は、ショップの値が、JANではない社内コード(IF…)のため、載せていない。中古品(USED)・セット品は除外 |
| TIMEMORE(追加分) | 5製品+1型番 | 6 | 販売店 Crema(cremashop.eu)の商品ページ(`crema-timemore`)と、販売店2か所の一致(`timemore-extra`) | Bricks 01S(Black・White)・Chestnut C3S MAX・C3S Pro(Black。Whiteは、MaxiCoffeeとwb.coffeeで同じEANを確認)・Sculptor 078・078S。timemore.comの項目と同じEANは、型番に `alsoIn`(別の出どころでも確認)の印を付けた(6型番)。Sculptor 064SのCremaのページは、2026-11-12に404だった |
| Fellow | 4製品(16型番) | 16 | 公式オンラインショップ(fellowproducts.com。ブラウザで書き出し) | 米国向けの店。JANは、米国のUPC/EAN(840…・852…・860…)で、日本の店で売る品の番号と違う場合がありうる。Stagg [X]/[XF]、Ode Gen 2、Opus 2、Stagg専用ペーパー |
| ORIGAMI | 11製品(47型番) | 47 | 公式オンラインショップ(origami-kai.com。ブラウザで書き出し) | JANは、日本のJAN(4536058…)。オンラインストア限定品を含む。ドリッパー形の照明(Pendant lamp)と、お茶用(Tea Dripper)は除外 |
| 珈琲サイフオン(コーノ式) | 54製品(サイフォンセット24・名門ドリッパーセット19・ペーパー11) | 0 | 公式サイト(coffee-syphon.co.jp)が読み込むCSV(`/csv/coffee_syphon.csv`・`/csv/meimon_filter.csv`) | CSVの「jan」の列は、**6桁の数字**(例: 421319)で、13桁のJANではない。完全なJANが分からないため、gtinは空(推測しない)。6桁は `siteCode` に残した。ロート・フラスコ・グラスポットなどの部品は載せていない |
| AeroPress(小川珈琲オンラインショップ) | 14製品(本体・Clear Colors・Go・Go Plus・専用ペーパー) | 14 | 小川珈琲オンラインショップ(oc-shop.co.jp。**販売店**。ブラウザで書き出し) | JANは、店の入力値。**12型番は、barcodeの欄が空で、型番(sku)に、JANの数字(チェックデジットが合うもの)が入っている**ため、その数字を使い、`gtinFrom: "sku"` の印を付けた。シール・カラフェ・フローコントロール・豆とのセットは除外 |
| Bodum(フレンチプレス) | 41製品 | 41 | 公式オンラインショップ(www.bodum.com/jp/ja)の商品ページに表示される「商品番号」「EAN」を、ブラウザで開いて読み取った記録 | 一覧(coffee-makers 1〜3ページ)の41商品。EANは、12桁(UPC-A。699965…・727015…)で、すべてチェックデジットが合う。ページのAPIは使っていない(ページはスクリプトで描画され、データは、サイトの内部のAPIから取る作り)。作り直すときは、同じ方法で読み取り、`tools-bodum.json` を作って、`bodum --from-file tools-bodum.json` を実行する |
| Comandante(コーヒーミル) | 7製品(うち X25 Trailmaster Dune は、販売店 wb.coffee と MaxiCoffee の2か所で同じEANを確認して追加。`comandante-x25`)(C40 MK4 Nitro Blade 6色・LAB Series 3種・Vintage Oak Classic・C60 Baracuda 2色。変種を合わせて13型番) | 13 | 販売店 Crema(cremashop.eu。エストニア)の商品ページ。利用者が指定 | **販売店の情報**(Comandante公式サイトは、作業用の端末から403で取得できなかった)。JANは、ページの構造化データ(schema.org の gtin13)の値で、店の入力値。`sku` の「Crema 3595」は、店の商品番号(メーカーの型番ではない)。変種の名前は、商品番号が入った画像の説明文・リンクから対応づけた(順番では対応づけない)。参考: Racing Greenの `4260113438107` は、別の販売店の掲載にも同じ数字がある |
| Kalita 業務用ミル(電動) | 15製品 | 14 | 公式サイト(kalita.co.jp/products/business_mill/) | ハイカットミル・ナイスカットG・ハイカットG・NEXT G2 など。`kalita-business-mill`。idは `kalita-biz-<番号>` |
| Mahlkönig・Dalla Corte(電動グラインダー) | 17製品 | 8 | メリタジャパンの公式サイト(melitta.co.jp/mahlkonig/・/dallacorte/)の製品ページ | EK43・EK Omnia・X54・X64・E65・E80・PEAK・DC MAX・DC one など。JANは、家庭用・一部の機種だけ。Sync Scale(スケール)は除外。`melitta-grinders` |
| Bodum(電動グラインダー) | 5商品 | 3 | 公式オンラインショップの「Electric Coffee Grinders」の商品ページに表示される値を、ブラウザで開いて読み取った記録 | BISTRO(ブレード式3・バー式2)。バー式(10903)は、ページにEANが表示されない。`bodum-grinders --from-file tools-bodum-grinders.json` |
| フジローヤル(富士珈機。業務用の電動ミル) | 5製品(R-220 みるっこ・R-300・R-440・R-750・FH-750) | 0 | 公式サイト(fuji-royal.jp/products/mill/)の製品ページの仕様表 | 型式・サイズ・重量・粉砕能力・ホッパー容量・電源・定格電力・カラーを、`spec` に保存(JANは、公式サイトに無い)。カラーは、色ごとの型番にした。`fuji-royal`。公式のオンラインストア(fuji-royal.stores.jp)は、この環境から403で取得できなかった |
| Bonmac(ボンマック。ラッキーコーヒーマシンの自社ブランド) | 29製品(グラインダー6・光サイフォン2・コーヒーメーカー5・業務用ペーパーフィルター16) | 0 | 公式サイト(lucky-coffee-machine.co.jp)の製品ページ | 製品データの表(電源・消費電力・刃の形状・グラインド能力・寸法・重量・ホッパー容量・杯数・枚数・対応機種など)を、`spec` に保存。製品コードを `sku` に。JANは、公式サイトに無い。「マシンを探す」の一覧は、スクリプトで描画されるため、ブラウザで一覧を開いて確認した商品番号を、スクリプトに書いてある(2026-11-12)。コーヒーブルーワー(BM-2030・BM-2100・BM-3100・BMP-2000Z)と全自動ドリップ式コーヒーマシン(BM-SAD2)は、コーヒーメーカーとして載せた(2026-11-12)。**載せていないもの**: ガラスデカンタ・BM-SAD2のオプション・リフレッシュ品。`bonmac` |
| コーヒーメーカー: Melitta(家庭用・業務用) | 9製品 | 家庭用の6製品に、JANあり(型番ごと) | メリタジャパンの公式サイト(melitta.co.jp。家庭用 `/melitta_hh/coffeemaker/`・業務用 `/melitta_pro/filtercoffeemachine/`)の製品ページ「スペック」の表 | 家庭用: オルフィプラス・イージートップサーモ・ミアス・アロマフレッシュ・ノアプラス・ツイスト。業務用: JET6・M150・XT180(アーン)。業務用は、型番・JANが表に無いものが多い(XT180のガラス製は、表なし)。JET6専用のショップグラインダーは、グラインダーではなくカタログから除外。`melitta-coffeemakers` |
| コーヒーメーカー: Kalita | 3製品 | 3 | 公式サイト(kalita.co.jp/products/coffeemaker/)の製品ページ | ET-102・EX-102N・MD-102N。「商品コード」「JANコード」の表記から。`kalita-coffeemakers` |
| コーヒーメーカー: HARIO | 5製品(+電動コーヒーサイフォン1はサイフォンに) | 0 | 公式サイト(hario.com/product/coffee/coffeemaker/)の製品ページ | EMC-02-B(MUGEN)・EQS-110-MGR-BT(SmartQ)・EVCM2-5TB(珈琲王2)・EVS-70SV-BT(Smart7BT)・EXM-110-MGR-BT(スマートX)。ECA-3-B は電動サイフォンのため種類は「サイフォン」。JANは、公式の製品ページに無い。`hario-coffeemakers` |
| コーヒーメーカー: Bodum | 2製品(BISTRO 電動コーヒーメーカー 1.5 L・2色) | 2 | 公式オンラインショップの商品ページの「商品番号」「EAN」を、ブラウザで開いて読み取った記録 | `bodum-coffeemakers --from-file tools-bodum-coffeemakers.json`。EANは12桁(UPC-A) |
| コーヒーメーカー・グラインダー: De'Longhi(デロンギ) | 25製品(49型番。コーヒーメーカー21・グラインダー4。全自動マシン・エスプレッソ・カプチーノメーカーを含む) | 49 | 公式サイト(delonghi.com/ja-jp)の商品ページ。一覧は公式の商品サイトマップ(/ja-jp/sitemap-ja-jp-product-sitemap-0.xml)。robots.txt は商品ページを禁止していない | ページに埋め込まれた商品データの `ean`(JAN。デロンギ日本の 4988371…。全件チェックデジットが合う)・商品名・型番(subModelIdentifier)と、仕様の表(消費電力・電圧・寸法・重量など)を `spec` に保存。色違いは、型番ごとの変種(色の名前は、商品名の末尾から)。取るのは、型番の頭が EC・EM・EXAM・ECAM・ETAM・ICM・ICMI・COX(コーヒーメーカー)と KG(グラインダー)のもの。ミルクコンテナ・ヒーター・豆・カップ・アクセサリーは除外。取得は1.5秒間隔。`delonghi`(`--reuse` で、保存した原文から作り直せる) |

### 既知の注意
- Kalitaの公式ページで、**102-D と 102-DL に、同じJAN(4901369503026)が付いている**。公式の記載のまま載せている(`npm run tools:check` が警告を出す)。JANから照合すると、先に見つかった方が出る。
- Melittaの「オリジナル 1×6 ナチュラルブラウン40枚」のJAN(4006508123834)は、公式ページの記載のまま(ドイツのEAN。チェックデジットは正しい)。
- HARIOの名前は、公式ページの表記のまま(例: 「V60透過ドリッパ-01クリア」のような表記ゆれも、そのまま)。

### Comandanteの、確認できていないEAN(採用しない)
「C40の色(Virginia Walnut・Alpine Lagoon・Burgundy・Copper Mountain・Snow Leopard)」「X25 Forest」の番号は、出所が見つからない、または、チェックデジットが合わないため、載せていない(2026-11-11に確認)。出所が見つかったら、追加する。

### TIMEMOREの、確認できていないEAN(採用しない)
2026-11-12に、利用者が挙げた一覧を照合した。**確認できた**: Chestnut C2 MAX(Black)6959493501621(2026-11-12。販売店 Crossroast(ベルギー)と Barista and Espresso(スウェーデン)の2か所で一致。`timemore-extra`)。**未確認**: C2S(Black)6959493507548(別の出どころに、6959493507500 もある)、C3 MAX 6959493502703、Sculptor 064(6959493505940。Crema Finland は、064S を 6959493505964 としていた)。出所が見つかったら追加する。timemore.com の C2 MAX の商品ページは、2026-11-12時点で404(検索結果には残っていたが、削除されていた)。ブラウザの書き出し(`shopify-export.js`)も、同日に再実行したが、一覧は21件のままで、C2 MAX・C3 MAX・C2S は、取れなかった(`EXTRA_HANDLES` で直接取りに行ったが、存在しない)。

## 電動ミル(電動グラインダー)の収録の状況(2026-11-12)
- カタログのグラインダー: 約112製品のうち、**電動の印があるのは48製品**(Kalita 20・Mahlkönig 16・TIMEMORE 8・HARIO 3・Dalla Corte 2。Bodumの5・フジローヤルの5・Bonmacの6を加えて64)。
- **次の候補(取得コードは用意済み。利用者のPCで、ブラウザの書き出しが必要)**: Wilfa(wilfa.com)・Niche Zero(nichecoffee.co.uk)・TWINBIRD(twinbird.jp)。`shopify-export.js` に対応済み。実行: `py -X utf8 scripts/build_tools_catalog.py wilfa --from-file tools-wilfa.json --dry-run`(niche・twinbirdも同様)。
- **公式サイトにJANが載らない国内メーカー**(De'Longhi・Cores・Siroca など): JANは、販売店の掲載(量販店・通販)にあるが、公式ではない。使うかどうかは、利用者の判断(これまでの方針は、公式を優先)。
- ツインバードの CM-D457B は、ミル内蔵の全自動コーヒーメーカーで、グラインダーではない。

## コーヒーメーカーの収録の状況(2026-11-12)
- 種類 `coffeemaker`(マイツールの「コーヒーメーカー」)。テイスティングログの「抽出方法」でも選べる(抽出の器具として)。
- 公式サイトから取れたのは、Melitta・Kalita・Bonmac・HARIO・Bodum(上の表)。
- **次の候補(取得コードは用意済み。利用者のPCで、ブラウザの書き出しが必要)**: Fellow(Aiden)・Wilfa(Svart Precision)・TWINBIRD(ミル付き全自動コーヒーメーカー)など。`shopify-export.js` の候補の判定にコーヒーメーカーの語を足し、`shopify_kind_en`・`shopify_kind_grinder_only` が `coffeemaker` を返すようにした(Fellowは、同じメーカーの項目が入れ替わる方式のため、書き出しを再実行して、`fellow --from-file` を実行し直す)。
- **De'Longhi**: 取り込み済み(上の表。公式の商品ページにJANあり。2026-11-12)。エスプレッソ・全自動マシンも、種類は「コーヒーメーカー」に入れた。
- **公式サイトにJANが載らない国内メーカー**(Siroca・パナソニック・象印・タイガー・Cuisinart など): 公式の製品ページに、JANが見当たらなかった(2026-11-12)。JANは、販売店の掲載にあるが、公式ではない。使うかどうかは、利用者の判断。

## 未収録(次の手)
- **小川珈琲(エアロプレス)**: 取り込み済み(上の表)。
- **ボダム(フレンチプレス)**: 取り込み済み(上の表)。
- **Comandante**: 公式サイトは取得できなかったが、販売店Cremaのページから取り込み済み(上の表)。公式サイトで確認できれば、そちらを優先する。
- **CAFEC**(cafec.co.jp)・**Kinu**(kinu-grinders.com): 作業用の端末から接続できなかった。
- Melittaの業務用、1Zpressoの個別の機種(Q・X・ZP6)。
- 販売店(楽天・Yahoo!・Amazonなど)の情報は、使わない(公式ではないため)。
