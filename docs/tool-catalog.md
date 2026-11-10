# 器具カタログ(data/tools.json)

設定「マイツール」の追加画面で、ドリッパー・ペーパー・コーヒーミルを、名前の一部やJAN(GTIN)から選んで登録するための、メーカー公式の情報のカタログ。
アプリは、追加画面を開いたときに、GitHub上の `data/tools.json` を1回だけ取得する(商品データと同じ配り方)。取得できなければ、候補が出ないだけで、手入力の登録はできる。

## 方針
- 値は、**メーカー公式のサイト**から取る(販売店・まとめサイトは使わない)。取れなかった項目は、空にする(推測しない)。
- 取得した原文は、`source-archive/tools-<メーカー>-<日付>/` に保存する(git管理外。非公開のバックアップ用リポジトリに入れる)。
- **価格は載せない**(変わりやすい)。**画像も載せない**(著作権)。
- JAN(GTIN)は、桁数とチェックデジットを検査し、合わないものは載せない。
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
- 取得の間隔は2秒。一覧は、全ページ(250件ずつ)取る。
- 種類(ドリッパー・ペーパー・ミル)は、商品名から決める。`--dry-run` で一覧を見て、載せたくないものが入っていれば、`shopify_kind_en` / `hario_kind` の除外の語を足す。
- JANは、桁数とチェックデジットが合うものだけ載せる(合わないものは、警告を出して、空にする)。店が入力した値のため、メーカーの公式の値と違う場合がありうる。
- 取得した原文は、`source-archive/tools-<名前>-<日付>/` に保存される。


取得の間隔は6秒(公式サイトへの負荷と、取得制限を避けるため)。

## 項目
`items[]`: `id`・`kind`(dripper / paper / grinder)・`maker`・`makerAlias`(検索用の読み)・`name`・`variants[]`(`label`色・大きさ、`sku`品番、`gtin`)・`url`(公式の製品ページ)・`checkedAt`・`sourceId`(原文の資料ID)。

## 収録の状況(2026-11-10)
| メーカー | 件数 | JAN | 取得元 | メモ |
|---|---|---|---|---|
| Kalita | 115製品 | 115 | 公式サイトの製品ページ(kalita.co.jp) | 製品ページの題名は型番だけのものが多いため、種類の名前(ドリッパー等)を前に付けた。ネルフィルター・セット・ポット等は除外 |
| HARIO | 79製品(87型番) | 0 | 公式サイトの製品情報(hario.com) | **JANは、公式サイトの製品ページに無い**。JANは公式オンラインショップ(shop.hariocorp.co.jp)にあるが、この環境からは取得できなかった(429)。取得できる環境で、`/products/<ハンドル>.js` の `variants[].barcode` から取れる |
| Melitta | 22製品(26型番) | 26 | 公式サイトの製品ページ(melitta.co.jp。家庭用のハンドドリップ器具・フィルターペーパー・ミル) | ページの「スペック」の表(型番・JAN)から。ケトル・サーバーは除外。メリタでは、ドリッパーを「コーヒーフィルター」「アロマフィルター」と呼ぶ。業務用は未収録 |
| 1Zpresso | 11機種 | 0 | 公式サイト(1zpresso.coffee) | 公式サイトに、型番・JANの表が無い。機種名は、各シリーズのページの見出しにあるものだけ(スクリプトが、ページにその文言があることを確かめてから載せる)。Q・X・ZP6の個別の機種名は、公式ページの見出しに無いため未収録 |

### 既知の注意
- Kalitaの公式ページで、**102-D と 102-DL に、同じJAN(4901369503026)が付いている**。公式の記載のまま載せている(`npm run tools:check` が警告を出す)。JANから照合すると、先に見つかった方が出る。
- Melittaの「オリジナル 1×6 ナチュラルブラウン40枚」のJAN(4006508123834)は、公式ページの記載のまま(ドイツのEAN。チェックデジットは正しい)。
- HARIOの名前は、公式ページの表記のまま(例: 「V60透過ドリッパ-01クリア」のような表記ゆれも、そのまま)。

## 未収録(次の手)
- **TIMEMORE・Fellow・ORIGAMI(origami-kai.com)・HARIOのJAN**: 上の「公式ショップから、JANを取る」を、利用者のPCで実行する(作業用の端末では、取得制限で取得できなかった)。
- **Comandante**(comandante.de): 403で、作業用の端末では取得できなかった。
- **CAFEC**(cafec.co.jp)・**Kinu**(kinu-grinders.com): 作業用の端末から接続できなかった。
- 販売店(楽天・Yahoo!・Amazonなど)の情報は、使わない(公式ではないため)。
