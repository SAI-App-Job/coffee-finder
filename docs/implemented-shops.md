# 実装店舗インデックス

`data/shops.json`・`data/products.json`から生成。件数は生成時点のスナップショット
(実際の最新値はdata/products.jsonを参照)。「方式」が「手動」の店舗は
`scraper/manual/shops/`配下、それ以外は`scraper/scrape_*.py`で自動取得。
実装を見送った店舗は`docs/not-implementable-shops.md`を参照。

合計72店舗・2010商品(生成日: 2026-09-03)。

再生成コマンド:
```
node scripts/gen-implemented-shops.js
```

### (所在地不明)

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| It's roasted coffee |  | 手動(SNSのみ) | 1 |
| 豆男珈琲 |  | BASE(theshop) | 23 |

### 京都府

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| びーんず亭 | 京都市中京区高倉通錦小路下ル中魚屋町511 | EC-CUBE | 23 |

### 埼玉県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| 幸音珈琲 | 朝霞市本町1-10-30 | Ocnk | 9 |

### 神奈川県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| TSUKIKOYA COFFEE ROASTER | 横須賀市浦郷町3-51 | カラーミー | 25 |
| TERA COFFEE and ROASTER | 横浜市港北区大倉山1丁目3-20 | カラーミー | 20 |
| NAGI COFFEE | 横浜市神奈川区松本町3-22-8 | BASE(theshop) | 12 |
| coffee roast 福田珈琲焙煎所 | 横浜市神奈川区神大寺4-1-7 フローラ神大寺1F | 手動(SNSのみ) | 6 |
| 405 COFFEE ROASTERS | 横浜市西区中央2-24-6 西前市場1階 | カラーミー | 25 |
| フォレスト自家焙煎コーヒー豆店 | 横浜市泉区緑園6-1-27 | Welcart | 15 |
| Mameya Roastery | 横浜市中区伊勢佐木町5-126 | カラーミー | 38 |
| COFFEE ROASTERY MEGURO | 横浜市中区元町・中華街 | BASE | 8 |
| COFFEE TERMINAL | 横浜市都筑区葛が谷14-7 | カラーミー | 40 |
| 自家焙煎星川珈琲 | 横浜市保土ケ谷区星川 | Shopify | 5 |
| 吉田珈琲焙煎所 | 茅ヶ崎市東海岸北1-1-1 | STORES(手動) | 5 |
| CafeCafa | 茅ヶ崎市東海岸北3-15-24 | 独自HTML | 10 |
| 厚木珈琲 | 厚木市飯山837-20 | Shopify | 9 |
| カフェクラウディア | 小田原市中町1-15-1 ホワイトシャトル102号 | BASE | 22 |
| Denim bis | 川崎市 | Ocnk | 21 |
| THE MODERN COFFEE | 川崎市宮前区鷺沼1-12-2 鷺沼ビラスズキ1F | Shopify | 4 |
| 楽園 | 川崎市宮前区平2-1-5 | crayon | 10 |
| かぎしっぽ | 川崎市幸区古市場1-31-7 | Goope | 3 |
| LEAFLETTER | 川崎市幸区柳町8-3 柳町ビル101 | BASE | 13 |
| シモト珈琲 | 川崎市高津区向ヶ丘129 | Tsuku2(手動) | 12 |
| 珈琲丸 | 川崎市高津区二子2-18-9 HOME194-C | Shopify | 3 |
| Green Beans(グリーンビーンズ) | 川崎市川崎区大島5-11-12 | Wix(手動) | 32 |
| Rhizomag | 川崎市多摩区宿河原7-14-13 毬ビル102 | カラーミー | 20 |
| MiLL Coffee | 川崎市多摩区南生田1-22-23 | Wix | 69 |
| 豆コネクト | 川崎市中原区小杉町2-294-6 エスカリエ1F | WordPress | 6 |
| SHIBACOFFEE | 川崎市中原区新丸子東1-826 シャトレKOYO 1階 | カラーミー | 22 |
| Mui | 川崎市中原区木月3-13-2 | ShopServe | 24 |
| Roast Design Coffee | 川崎市麻生区上麻生1-6-3 マプレGF階 | カラーミー | 40 |
| Coulane | 相模原市中央区横山3-17-4 | カラーミー | 47 |
| 27 COFFEE ROASTERS | 藤沢市辻堂元町5-2-24 | Shopify | 28 |
| いつか珈琲屋 | 平塚市河内1-7-1 | BASE | 19 |

### 千葉県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| PHILOCOFFEA |  | カラーミー | 410 |

### 東京都

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| WOODBERRY COFFEE |  | Shopify | 33 |
| HIDE COFFEE BEANS STORE | 江東区東雲1-2-1 | カラーミー | 15 |
| カフェ・デザールピコ | 江東区門前仲町 | カラーミー | 27 |
| 松屋珈琲店 | 港区虎ノ門3-8-16 | カラーミー | 26 |
| Coffee Roast SAI | 港区高輪1-21-3 チバビル1F | Shopify | 36 |
| Daphne | 港区芝5-10-11 | EC-CUBE | 12 |
| 麻布珈房 | 港区麻布十番 | カラーミー | 156 |
| 珈琲店トップ | 渋谷区代々木5-63-10 | カラーミー | 21 |
| FUGLEN COFFEE ROASTERS | 渋谷区富ヶ谷1-16-11 | Shopify | 12 |
| A FEW WORDS COFFEE | 新宿区新宿7-24-4 1F | 手動 | 8 |
| ザグリ珈琲 | 杉並区阿佐谷北1-43-6 | Shopify | 8 |
| 青空豆店 | 杉並区永福4-10-4 | BASE | 13 |
| たまじ珈琲 | 杉並区成田東2-33-12 | WP+USCe | 47 |
| chouette torréfacteur laboratoire | 世田谷区宮坂1-39-11 | BASE(theshop) | 11 |
| FINETIME COFFEE ROASTERS | 世田谷区経堂1-12-15 | BASE(theshop) | 12 |
| カフェマルシェkunikuni | 世田谷区経堂2-4-8　Antelop経堂A号室 | カラーミー | 19 |
| 珈琲家あのころ | 世田谷区若林4-20-9 岡村ビル1F | BASE(theshop) | 14 |
| 南薫堂珈琲 | 世田谷区世田谷2-6-4　グリーンアネックス102 | BASE | 13 |
| 豆善 | 世田谷区尾山台3-22-4マンヤスビル022号室 | Shopify | 24 |
| 十一房珈琲店 | 中央区銀座2-2-19 藤間ビル1F | 手動 | 25 |
| 米本珈琲 | 中央区築地 | Ocnk | 18 |
| ライブコーヒー | 中央区築地3-5-13 北村ビル1F | Ocnk | 38 |
| こなみ珈琲 | 中央区日本橋蛎殻町1-39-2 | BASE | 41 |
| TORIBA COFFEE | 中央区八重洲2-1-1 YANMAR TOKYO B1F | MakeShop | 18 |
| ITSUKI Coffee Roastery | 中野区 | WooCommerce | 3 |
| MARUTAKE COFFEE BEANS | 中野区野方6-18-14 | BASE | 60 |
| 神楽坂珈琲焙煎所 | 文京区関口1-3-5 ロジビル1F | MakeShop | 40 |
| ビーズコーヒー | 文京区千石1-29-15 LAアパートメント文京千石1F | カラーミー | 14 |
| 自家焙煎珈琲みじんこ | 文京区湯島2-9-10 湯島三組ビル1F | カラーミー | 3 |
| BEANS珈琲 | 墨田区 | BASE | 21 |
| Single O Japan | 墨田区亀沢3-21-5 | Shopify | 17 |
| CAFE FACON | 目黒区上目黒3-8-3 千陽中目黒ビル・アネックス3F | ShopServe | 26 |
| HIMONYA FIVE COFFEE | 目黒区碑文谷5-11-6 | BASE(theshop) | 34 |
| nericafe | 練馬区大泉学園町1-16-15 | カラーミー | 8 |
| GONZO CAFE&BEANS | 練馬区東大泉7-38-29 加昌マンション108 | BASE | 54 |
| 隠房 | 練馬区練馬4-20-3 ミヤマビル101 | BASE | 4 |
