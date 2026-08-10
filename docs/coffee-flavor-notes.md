# テイスティングノート・フレーバー表現 調査まとめ

コーヒーは嗜好品であり、科学的な単一指標だけでは評価しきれないため、各店舗が
言葉による風味表現(テイスティングノート)を独自に付与する。この表現に関する
用語の整理と、業界標準の分類(SCAフレーバーホイール)をまとめる。

---

## 1. 用語の整理(表記ゆれ)

| 用語 | 技術的な意味 | 実務上の扱い |
|---|---|---|
| **味わい** | 酸味・苦味・コク・後味・マウスフィール(質感)まで含む、口に含んだ総合的な体験全体 | 最も広い概念 |
| **風味** | 香りと味の組み合わせ。「フレーバー」とほぼ同義で使われることが多い | フレーバーとほぼ同義語として流通 |
| **フレーバー** | 英語からの借用語。口に含んだ時の味+鼻に抜ける香り(レトロネーザルアロマ)の組み合わせを指す専門用語 | 味わい・風味とほぼ同義語として流通 |
| **テイスティングノート** | 英語からの借用語(tasting notes)。カッパー(鑑定士)が感じた風味を書き留めた「記録・表現の言葉そのもの」を指す | 上記3語とほぼ同義語として流通 |
| **アロマ** | 抽出液(コーヒー液)から立ち上る香りのみ | 香りの専門用語。フレグランスと区別される |
| **フレグランス** | 挽いた粉(未抽出)から香る香りのみ | アロマとは区別される専門用語 |

**結論**: 味わい/風味/フレーバー/テイスティングノートの4語は、技術的には微妙な定義の違いがあるものの、**店舗の実務ではほぼ同義語として使われている**。パース時はこれら全てを同一の情報(テイスティングノート)として扱うのが実務的。

## 2. 重要な注意点:「フレーバー」の多義性

「フレーバー」という語は2つの異なる意味で使われるため、混同すると誤判定につながる。

1. **風味表現としての「フレーバー」**(本ページの主題): 「フルーティーなフレーバー」のように、コーヒー自体が持つ味・香りを指す
2. **「フレーバーコーヒー」の略としての「フレーバー」**: 焙煎時・焙煎後に人工的な香り付けをしたコーヒーを指す、全く別の商品カテゴリ

→ 商品パーサーで「フレーバー」を単独キーワードとしてフレーバーコーヒー判定に使うと、①のケース(風味表現としての通常のシングルオリジン商品)を誤って除外してしまう危険がある。**「フレーバーコーヒー」「フレーバー珈琲」のような複合語でのみ判定する**必要がある(実装時にこの誤りに気づき修正済み)。

## 3. SCAフレーバーホイール(業界標準の分類)

2016年にSCA(スペシャルティコーヒー協会)とWCR(ワールドコーヒーリサーチ)が共同開発した、コーヒーの風味を統一言語で語るための分類ツール。WCRのセンサリーレキシコン(感覚用語辞典)を基に作成され、業界のカッピング大会やプロの現場で標準的に使われている。

### 9大カテゴリ(内側の輪)

| カテゴリ(英語) | 日本語 | 代表的な具体例 |
|---|---|---|
| Fruity | フルーティー | ベリー、ドライフルーツ、柑橘、その他フルーツ |
| Floral | フローラル | ジャスミン、ローズ |
| Sweet | スイート/甘み | キャラメル、はちみつ、バニラ、ブラウンシュガー |
| Nutty/Cocoa | ナッツ/カカオ | アーモンド、ヘーゼルナッツ、ダーク/ミルクチョコレート |
| Spices | スパイス | シナモン、クローブ、ペッパー、アニス |
| Roasted | ロースト | スモーキー、タバコ、シダー、焦げ |
| Green/Vegetative | グリーン/野菜っぽさ | 青草、豆っぽさ |
| Sour/Fermented | 酸味/発酵 | ビネガー、アルコール、熟成チーズ様 |
| Other | その他 | 紙っぽさ/カビっぽさ、ケミカル、オリーブオイル(ネガティブな風味も含む) |

全体で110種類の具体的な表現がある。ホイールは中心(大分類)→中間(中分類、例:Fruity→Berry/Citrus/Tropical)→外側(具体的な表現、例:Berry→Blueberry/Strawberry)という3層構造。

### 具体的な表現の全体リスト(外側の輪、公式PDFより)

| 大分類 | 中分類 | 具体的な表現 |
|---|---|---|
| **Fruity** | Berry | Blackberry, Raspberry, Blueberry, Strawberry |
| | Dried Fruit | Raisin, Prune |
| | Other Fruit | Coconut, Cherry, Pomegranate, Pineapple, Grape, Apple, Peach, Pear |
| | Citrus Fruit | Grapefruit, Orange, Lemon, Lime |
| **Sour/Fermented** | Sour | Sour Aromatics, Acetic Acid, Butyric Acid, Isovaleric Acid, Citric Acid, Malic Acid |
| | Alcohol/Fermented | Winey, Whiskey, Fermented, Overripe |
| **Green/Vegetative** | (直下) | Under-ripe, Peapod, Fresh, Dark Green, Vegetative, Hay-like, Herb-like |
| | Beany | — |
| | Olive Oil / Raw | — |
| **Other** | Papery/Musty | Stale, Cardboard, Papery, Woody, Moldy/Damp, Musty/Dusty, Musty/Earthy |
| | Chemical | Bitter, Salty, Medicinal, Petroleum, Skunky, Rubber |
| | Animalic / Meaty-Brothy / Phenolic | — |
| **Roasted** | Pipe Tobacco / Tobacco | — |
| | Burnt | Acrid, Ashy, Smoky |
| | Cereal | Brown, Roast, Grain, Malt |
| **Spices** | Pungent / Pepper | — |
| | Brown Spice | Anise, Nutmeg, Cinnamon, Clove |
| **Nutty/Cocoa** | Nutty | Peanuts, Hazelnut, Almond |
| | Cocoa | Chocolate, Dark Chocolate |
| **Sweet** | Brown Sugar | Molasses, Maple Syrup, Caramelized, Honey |
| | Vanilla | Vanilla, Vanillin |
| | (直下) | Overall Sweet, Sweet Aromatics, Black Tea |
| **Floral** | (直下) | Chamomile, Rose, Jasmine, Black Tea |

> **注記**: 円形図からのテキスト抽出のため、一部の用語がどの中分類に属するかの厳密な階層は原典PDFの図(視覚的な配置)でのみ正確に確認できる。上表は既知のSCAホイール構造と照合した上での整理であり、細部の階層分けには若干の推定を含む。

### ネガティブな風味も含まれる点に注意

フレーバーホイールは「フルーティー」「フローラル」のようなポジティブな表現だけでなく、「焦げ」「土っぽい」「カビ臭い」のようなネガティブな項目(Otherカテゴリ等)も含む。テイスティングノートの原文をそのまま保持する設計であれば、ポジティブ/ネガティブの判別は行わず原文をそのまま格納する。

## 4. データモデルへの反映

- `PRODUCT.flavor_notes`: テイスティングノートの原文をフリーテキストで保持(店舗の見出し表記ゆれは`TASTING_NOTE_LABEL_SYNONYMS`で吸収)
- `PRODUCT.decaf_process`: カフェイン除去方法の原文(デカフェ商品のみ)
- 将来的な拡張案: `flavor_notes`のフリーテキストをSCAフレーバーホイールの9大カテゴリに自動分類するタグ付け機能(`TASTE_TAG`のような多対多テーブル)。現時点では店舗ごとの表現がバラバラ(日本語/英語混在、単語/文章混在)なため、まず原文保持を優先し、分類の自動化は精度検証をしてから検討する
