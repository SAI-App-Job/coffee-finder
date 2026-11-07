# ストア掲載文(英語)

Google Play(Android・TWA)を主、App Store を従として、英語の掲載文を用意したもの。
日本語の掲載文は [store-listing-ja.md](store-listing-ja.md)(英語版と内容を揃えること)。

- 英語の文面は、アプリの現状の機能・データ量にもとづく(2026-11-08時点)。
- **数字(1,800店舗以上・25,000商品以上)は、データが増えれば古くなる。** 公開前に、`data/shops.json` と `data/products.json` の件数で再確認する。
- **広告・解析・課金を入れたら、「PRIVATE BY DESIGN」の「No ads and no analytics」の行と、データセーフティの回答を必ず直す**(`public/privacy-policy*.html` と `src/components/AboutView.jsx` も同時に)。

## 文字数の確認

| 項目 | 文字数 / 上限 | 判定 |
|---|---|---|
| Google Play: App name | 29 / 30 | OK |
| Google Play: Short description | 70 / 80 | OK |
| Google Play: Full description | 1980 / 4000 | OK |
| App Store: Name | 13 / 30 | OK |
| App Store: Subtitle | 27 / 30 | OK |
| App Store: Promotional text | 145 / 170 | OK |
| App Store: Description | 1980 / 4000 | OK |
| App Store: Keywords | 98 / 100 | OK |

## Google Play

### App name
```
Coffee Finder: Japan Roasters
```

### Short description
```
Find home-roasted coffee beans from independent roasters across Japan.
```

### Full description
```
Discover your next favorite coffee bean from independent home roasters across Japan.

Coffee Finder brings together more than 1,800 small roasting shops and over 25,000 coffee beans in one place, so you can find beans you wouldn't come across otherwise - by origin, flavor, location, or just by browsing.

FIND
• Search by product, origin, brand, shop, address, or nearest station
• Filter by origin country, flavor category (based on the SCA/WCR flavor wheel), prefecture, and your own star ratings
• Sort by distance from you, your registered area, newly listed beans, or at random for a little serendipity
• Open any shop in Google Maps

KEEP
• Save beans to your collection with one tap
• Register beans you bought at a shop - even in-store-only beans that aren't sold online - and add a photo of the package
• Rate beans with stars, record tasting logs for coffee you brew at home (recipe, flavors, and a Dial-in Score), and jot down tasting notes for cups you drink at shops
• See your taste profile, built from your ratings, with bean recommendations
• Back up and restore your collection as a file

STAY UPDATED
• See in-app notifications about price drops and restocks on saved beans, and new products from their shops
• Compare beans side by side

LEARN
• Trivia: flavor wheel, glossary, designated brands, coffee varieties, brewing guide, events, and competitions
• An origin map with guides to major coffee-producing countries

PRIVATE BY DESIGN
• No account needed
• Your collection, ratings, logs, notes, and photos stay on your device
• Your location is used only to sort by distance, and is never sent to a server
• No ads and no analytics at the moment

GOOD TO KNOW
• The app interface is available in English and Japanese. It follows your device language, and you can switch it in Settings.
• Shop and product data (names, tasting notes, farm information, addresses) and the Trivia and Origin guide texts are in Japanese only.
• All shops are located in Japan.
```

### What's new(初回リリース)
```
First release.
```

### 分類・基本情報(案)
| 項目 | 内容 |
|---|---|
| App category | Food & Drink |
| Tags(候補) | Food & Drink, Maps & Navigation(選べるものの範囲で) |
| Contact email | **要入力**(ストア審査では連絡先のメールアドレスが必須。現状はXの @SaiCoffea のみ) |
| Website | 任意 |
| Privacy policy URL | **要入力** `https://(配信先)/privacy-policy-en.html`(日本語は `/privacy-policy.html`) |
| Contains ads | No(現状は広告欄のプレースホルダーのみ。広告SDKを入れたら Yes) |
| In-app purchases | No(現状は決済なし。設定の「プレミアム」は開発用の表示) |
| Content rating(案) | 全年齢向けの回答(暴力・性的表現・賭博・ユーザー生成コンテンツの共有なし)。質問票の回答は、公開時に最新の内容で確認する |
| Target audience | 13歳以上〜成人(子ども向けにはしない) |

### Data safety(データセーフティ)回答の下書き
**ストアの質問票は更新されることがあるため、回答は、公開時に最新の質問と照らして確認する。外部送信の扱い(下の3点目)は特に、専門家への確認をおすすめする。**

- ユーザーのアカウント・氏名・メールアドレスなどは、収集しない。
- コレクション・評価・ログ・ノート・写真は端末内にのみ保存し、開発者のサーバーへは送信しない。
- 位置情報は、端末内での距離計算にのみ使い、送信しない。
- 表示に必要な外部サービス(GitHub、OpenStreetMap、Google Fonts)とは通信し、IPアドレス等がそれらに届く。これを「データの共有・収集」として申告するかは、質問票の定義(開発者が受け取るか、第三者へ共有するか)に照らして判断する。
- データの暗号化(通信): 外部サービスとの通信は HTTPS。
- ユーザーがデータの削除を求める手段: 端末内のデータなので、アプリのデータ削除・アンインストールで消える(開発者側に削除対象のデータはない)。

## App Store(iOS版を出す場合)

### Name
```
Coffee Finder
```

### Subtitle
```
Home-roasted beans in Japan
```

### Promotional text
```
Find home-roasted beans from independent Japanese roasters. Save favorites, log your tastings, and keep your coffee notes private on your device.
```

### Description
Google Play の Full description と同じ文面を使う。

### Keywords
```
coffee,beans,roaster,Japan,specialty,cafe,tasting,brew,origin,flavor,pour over,single origin,Tokyo
```

### What's New
```
First release.
```

### 補足
- App Privacy(プライバシー栄養表示)は、「Data Not Collected」に近い回答になる見込み。位置情報は端末内の処理のみ。外部サービスへの通信の扱いは、Appleの定義に照らして確認する。
- Category: Food & Drink(第2: Lifestyle など)。
- iOS向けの提供は、現状のTWA(Android)構成とは別の作業になる。

## スクリーンショットの案(英語UIで撮る)
英語UI(設定 → English)で、できればサンプルデータ(英語で作成)を入れた状態で撮る。

| # | 画面 | キャプション(案) |
|---|---|---|
| 1 | 商品一覧(近い順) | Find home-roasted beans from independent roasters across Japan |
| 2 | 絞り込み | Filter by origin, flavor, prefecture, and your ratings |
| 3 | 商品詳細 | Everything about a bean in one place |
| 4 | 店舗詳細 | Browse each shop and open it in Google Maps |
| 5 | コレクション(登録した商品・写真・★) | Keep the beans you bought, with package photos |
| 6 | テイスティングログ(Dial-in Score) | Log your brews and see what works |
| 7 | 好みの傾向 | Discover your taste profile |
| 8 | 産地マップ | Explore the world's coffee origins |

- **キャプションや画面に、日本語のデータ(商品名など)が写ることは、問題ない。** ただし、説明文の「GOOD TO KNOW」と食い違わないよう、データは日本語であることを隠さない。
- 画面に実在の店舗名・商品名が写る場合は、それらの権利(商標・著作権)の扱いに注意する。サンプルデータなら、架空なので問題ない。
- Google Play の必須アセット: アイコン(512×512)、フィーチャーグラフィック(1024×500)、スクリーンショット(最低2枚)。
