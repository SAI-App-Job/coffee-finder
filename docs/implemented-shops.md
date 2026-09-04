# 実装店舗インデックス

`data/shops.json`・`data/products.json`から生成。件数は生成時点のスナップショット
(実際の最新値はdata/products.jsonを参照)。「方式」が「手動」の店舗は
`scraper/manual/shops/`配下、それ以外は`scraper/scrape_*.py`で自動取得。
実装を見送った店舗は`docs/not-implementable-shops.md`を参照。

合計158店舗・3973商品(生成日: 2026-09-04)。

再生成コマンド:
```
node scripts/gen-implemented-shops.js
```

### (所在地不明)

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| It's roasted coffee |  | 手動(SNSのみ) | 1 |
| 豆男珈琲 |  | BASE(theshop) | 23 |

### 茨城県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| 298珈琲焙煎所 | つくば市高野466-5 | BASE | 8 |
| まめぽっと | つくば市谷田部1-1 | カラーミー | 11 |
| TRIBE COFFEE | つくば市東新井20-7-101 | カラーミー | 12 |
| 庭cafe焙煎所 | 下妻市下妻乙908-1 | BASE | 6 |
| 十人十豆 | 笠間市笠間2517-1 | BASE | 5 |
| 奥久慈珈琲焙煎所ルージュノワール | 久慈郡大子町袋田一條2978-1 | BASE | 16 |
| 南部珈琲 | 牛久市栄町1-21 | BASE | 32 |
| TONE UP COFFEE | 取手市東6-37-7只石ビル102 | BASE | 12 |

### 京都府

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| びーんず亭 | 京都市中京区高倉通錦小路下ル中魚屋町511 | EC-CUBE | 23 |

### 埼玉県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| 熊谷珈琲 | さいたま市大宮区浅間町2-46 | カラーミー | 27 |
| ALL THAT COFFEEWORKS | さいたま市大宮区土手町2-35 | BASE | 11 |
| 柊豆 | 熊谷市船木 | BASE | 9 |
| KiaOra COFFEE | 春日部市大沼3-123-1 | BASE | 12 |
| しかくCOFFEE | 所沢市若狭1-2626-43 | BASE | 13 |
| 豆わらべ | 深谷市上野台1949-3 | BASE(theshop) | 19 |
| COFFEE GALLERY | 川越市松江町2-3-5 | BASE | 11 |
| トレモロコーヒーロースター | 草加市草加3-8-15 | BASE | 17 |
| 幸音珈琲 | 朝霞市本町1-10-30 | Ocnk | 9 |
| coffee mameco | 東松山市六反町3-32 | Shopify | 10 |
| アスロンコーヒー焙煎所 | 飯能市名栗 | Ocnk | 9 |
| あさみ珈琲豆店 | 本庄市児玉町児玉335-15 | Ocnk | 20 |

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
| SLOW COFFEE |  | Shopify | 47 |
| MAHAMERU COFFEE |  | Shopify | 2 |
| アダチコーヒー |  | Ocnk | 28 |
| 自家焙煎 香珈 Beans＆Cafe |  | Goope | 15 |
| 豆NAKANO |  | カラーミー | 17 |
| TABEI COFFEE | 四街道市 | Welcart | 12 |
| CAMBLEM グリーン珈琲焙煎所 | 市川市市川南1丁目(市川店) | Shopify | 44 |
| 萌季屋 | 市川市八幡 | カラーミー | 18 |
| Eureka Coffee Roasters | 千葉市稲毛区緑町1-8-16 | Shopify | 42 |
| ROASTER's HOUSE | 千葉市花見川区花園1-20-7 | BASE | 24 |
| エトナコーヒー | 千葉市花見川区幕張 | MakeShop | 89 |
| RUMOR'S COFFEE | 千葉市緑区おゆみ野南2-16-3 | BASE | 37 |
| Coffee Roast 焙香 | 船橋市 | BASE | 38 |
| 珈琲豆のおおつか | 船橋市 | らくうるカート | 48 |
| 珈琲工房豆壱 | 柏市中央2-9-11-102 | BASE | 34 |
| きたみcoffee | 八千代市 | EC-CUBE | 23 |

### 東京都

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| WOODBERRY COFFEE |  | Shopify | 33 |
| THE WORD COFFEE ROASTERS | 葛飾区奥戸1-19-3 斉藤マンション1B | Shopify | 41 |
| マウンテンコーヒー葛飾 | 葛飾区高砂2-4-3 | BASE | 16 |
| にじいろコーヒー店 | 葛飾区水元 | BASE | 7 |
| 御豆屋 | 江戸川区(小岩駅北口) | BASE | 65 |
| コーヒーランド | 江戸川区松島2丁目 | 独自HTML | 40 |
| いろどりこーひー | 江戸川区中葛西1-38-8 | Shopify | 32 |
| 珈琲自家焙煎HiwaHiwa | 江戸川区中葛西2-7-2 | BASE | 6 |
| オトメザ | 江戸川区東葛西 | Jimdo | 10 |
| 珈琲ハウスK2 | 江戸川区平井3丁目 | Ocnk | 23 |
| 青海珈琲 | 江東区青海(本店) | MakeShop | 48 |
| HIDE COFFEE BEANS STORE | 江東区東雲1-2-1 | カラーミー | 15 |
| カフェ・デザールピコ | 江東区門前仲町 | カラーミー | 27 |
| 松屋珈琲店 | 港区虎ノ門3-8-16 | カラーミー | 26 |
| Coffee Roast SAI | 港区高輪1-21-3 チバビル1F | Shopify | 36 |
| Daphne | 港区芝5-10-11 | EC-CUBE | 12 |
| 麻布珈房 | 港区麻布十番 | カラーミー | 156 |
| Blackhole Coffee Roaster | 荒川区町屋4-31-11 | Shopify | 11 |
| カメヤマ珈琲 | 荒川区東日暮里6-22-14 | WordPress | 34 |
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
| 豆香房 | 千代田区神田神保町 | カラーミー | 53 |
| ゆるり珈琲 | 足立区(五反野駅・小菅駅近く) | BASE | 22 |
| BLACK SLOTH COFFEE | 足立区西新井 | BASE | 13 |
| SLOW JET COFFEE | 足立区千住東1丁目 | BASE | 8 |
| 自家焙煎メロディアスコーヒー | 足立区保木間1-1-13 足立水道会館2階 | BASE | 25 |
| northnodecoffee | 足立区保木間3-15-14 | BASE | 18 |
| nano-coffeeroaster | 台東区浅草橋1-17-4 | BASE | 8 |
| Peppino Coffee Roaster | 台東区浅草橋2-24-8 | WooCommerce | 25 |
| 焙煎処 縁の木 | 台東区蔵前 | カラーミー | 51 |
| ベースキャンプ | 台東区台東3-2-11 | 手動 | 28 |
| FIVE COFFEE STAND&ROASTERY | 台東区谷中1-3-6 | BASE | 14 |
| 入谷珈琲豆店 | 台東区入谷1-19-6 | BASE | 27 |
| きまめ屋 | 大田区西蒲田 | 手動 | 28 |
| 加とう珈琲焙煎所 | 大田区大森北5-10-3 | BASE | 13 |
| ROOT COFFEE | 大田区池上 | BASE | 24 |
| 下町コーヒー | 大田区南六郷 | 独自EC(xaas3.jp) | 6 |
| WORLD BEANS | 大田区矢口2-11-28 | 手動 | 17 |
| 十一房珈琲店 | 中央区銀座2-2-19 藤間ビル1F | 手動 | 25 |
| 米本珈琲 | 中央区築地 | Ocnk | 18 |
| ライブコーヒー | 中央区築地3-5-13 北村ビル1F | Ocnk | 38 |
| こなみ珈琲 | 中央区日本橋蛎殻町1-39-2 | BASE | 41 |
| TORIBA COFFEE | 中央区八重洲2-1-1 YANMAR TOKYO B1F | MakeShop | 18 |
| ITSUKI Coffee Roastery | 中野区 | WooCommerce | 3 |
| MARUTAKE COFFEE BEANS | 中野区野方6-18-14 | BASE | 60 |
| カフェ・ベルニーニ | 板橋区志村3-7 | Shopify | 21 |
| 杉綾珈琲豆店 | 板橋区中板橋16-6 | BASE | 13 |
| 下頭橋焙煎所 | 板橋区弥生町52-1 | BASE | 21 |
| 珈琲豆焙煎処Taguriano | 品川区荏原 | BASE | 13 |
| コンパスコーヒー | 品川区旗の台 | Ocnk | 28 |
| MITSUMATA COFFEE | 品川区大井4-1-2 | Shopify | 13 |
| NORTH STAR BEANS | 品川区北品川1-3-18 | Shopify | 46 |
| 神楽坂珈琲焙煎所 | 文京区関口1-3-5 ロジビル1F | MakeShop | 40 |
| ビーズコーヒー | 文京区千石1-29-15 LAアパートメント文京千石1F | カラーミー | 14 |
| 自家焙煎珈琲みじんこ | 文京区湯島2-9-10 湯島三組ビル1F | カラーミー | 3 |
| Toden Coffee | 豊島区雑司が谷 | BASE | 128 |
| 焙煎カフェ やきやき | 北区赤羽北2-31-16 | BASE | 10 |
| 村上コーヒー | 北区中里1-5-11 | 手動(SNSのみ) | 6 |
| BEANS珈琲 | 墨田区 | BASE | 21 |
| Single O Japan | 墨田区亀沢3-21-5 | Shopify | 17 |
| CAFE FACON | 目黒区上目黒3-8-3 千陽中目黒ビル・アネックス3F | ShopServe | 26 |
| HIMONYA FIVE COFFEE | 目黒区碑文谷5-11-6 | BASE(theshop) | 34 |
| nericafe | 練馬区大泉学園町1-16-15 | カラーミー | 8 |
| GONZO CAFE&BEANS | 練馬区東大泉7-38-29 加昌マンション108 | BASE | 54 |
| 隠房 | 練馬区練馬4-20-3 ミヤマビル101 | BASE | 4 |

### 栃木県

| 店舗名 | 所在地 | 方式 | 件数 |
|---|---|---|---|
| 豆工房コーヒーロースト宇都宮店 | 宇都宮市菊水町8-21 | カラーミー | 31 |
| かめとかめ | 宇都宮市錦3-1-7 | BASE | 8 |
| 織部珈琲 | 宇都宮市兵庫塚2-8-7 | BASE | 19 |
| 宇都宮珈琲 | 宇都宮市平松本町1138-7 | カラーミー | 1 |
| チバコーヒー | 宇都宮市陽東3-8-4 | BASE | 18 |
| 中西珈琲 | 下都賀郡野木町丸林675-5 | BASE | 6 |
| 日光珈琲 | 鹿沼市上材木町1739 | BASE | 13 |
| ひつじ珈琲 | 大田原市中野内735 | WooCommerce | 34 |
| 悟理道珈琲工房 | 栃木市万町9-32 | BASE | 5 |
| 自家焙煎珈琲コトリ | 那須塩原市井口1181-3 | カラーミー | 21 |
| 瑞玉珈琲 | 那須郡那須町高久乙594-81 | BASE | 12 |
| 那須珈琲 Cafe La Détente | 那須郡那須町寺子丙3 | カラーミー | 5 |
