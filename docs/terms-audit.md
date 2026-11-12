# 店舗サイトの規約の、機械的な確認

確認日: 2026-11-12 / 作り方: `python -X utf8 scripts/audit_terms.py`(判定だけ直すとき: `--recheck`)

ホスト 1946 件: **要確認(自動取得などを禁じる記載の疑い) 14** / 定型の転載禁止のみ 42 / 記載なし 259 / 規約のページが見つからず 1347 / 取得できず 284

これは機械的な絞り込みで、最終判断は人が行う。店舗の文章は、ここには写していない(URLと、見つけた語だけ)。語の末尾の「*」は、禁止の語が少し離れている(前後300字)弱い疑い。

## 読み方
- 規約のページが見つかったのは 315 ホスト。ほとんどの小さな店舗は、利用規約のページ自体を持たない(見つからず 1,347)。
- 取得できず 284 は、接続失敗・403・タイムアウトなど。規約を確認できていない。

## 要確認: 14 件(すべて、Shopify標準の利用規約テンプレートと同じ文面とみられる。禁止行為の一覧に、クローリング・スクレイピングの語)

- AMANO COFFEE ROASTERS — https://amano-coffee.com — 語: クローリング*, スクレイピング* — https://amano-coffee.com/pages/terms-of-service / https://amano-coffee.com/pages/refund-policy
- ARCHE COFFEE — https://archecoffee.com — 語: クローリング*, スクレイピング* — https://archecoffee.com/pages/%E5%88%A9%E7%94%A8%E8%A6%8F%E7%B4%84 / https://archecoffee.com/policies/terms-of-service / https://archecoffee.com/policies/refund-policy
- Beans. Coffee&Roasters — https://beanscoffee.jp — 語: クローリング*, スクレイピング* — https://beanscoffee.jp/policies/terms-of-service
- カフェ・ベルニーニ — https://caffebernini.com — 語: クローリング*, スクレイピング* — https://caffebernini.com/policies/terms-of-service / https://caffebernini.com/pages/%E3%81%94%E5%88%A9%E7%94%A8%E3%82%AC%E3%82%A4%E3%83%89 / https://caffebernini.com/policies/refund-policy
- 珈琲回廊 — https://coffeegallery.online — 語: クローリング*, スクレイピング* — https://coffeegallery.online/policies/terms-of-service / https://coffeegallery.online/policies/refund-policy
- COFFEE PORT 芦屋浜ロースタリー — https://coffeeport.net — 語: クローリング*, スクレイピング* — https://coffeeport.net/pages/terms-of-service
- en. 珈琲焙煎所 — https://en-coffee.jp — 語: クローリング*, スクレイピング* — https://en-coffee.jp/policies/terms-of-service / https://en-coffee.jp/policies/refund-policy
- KLATCH COFFEE — https://klatch-coffee.com — 語: クローリング*, スクレイピング* — https://www.klatch-coffee.com/policies/terms-of-service / https://www.klatch-coffee.com/policies/refund-policy
- ミルトンコーヒーロースタリー — https://miltoncoffee.com — 語: クロール*, スクレイピング* — https://miltoncoffee.com/policies/terms-of-service / https://miltoncoffee.com/pages/shop_information / https://miltoncoffee.com/policies/refund-policy
- round coffee ITOSHIMA — https://round-coffee.com — 語: クローリング*, スクレイピング* — https://round-coffee.com/policies/terms-of-service
- さとやまコーヒー — https://satoyamacoffee.com — 語: クローリング*, スクレイピング* — https://satoyamacoffee.com/policies/terms-of-service
- 岳山珈琲 — https://shop.gakuzancoffee.com — 語: クローリング*, スクレイピング* — https://shop.gakuzancoffee.com/policies/terms-of-service / https://shop.gakuzancoffee.com/policies/refund-policy / https://shop.gakuzancoffee.com/policies/subscription-policy
- 焙煎工房てんぷす — https://tenpus.coffee — 語: クローリング*, スクレイピング* — https://tenpus.coffee/policies/terms-of-service / https://tenpus.coffee/policies/refund-policy
- 熊本珈琲Roaster — https://www.kumamoto-coffee-roaster.store — 語: クローリング*, スクレイピング* — https://www.kumamoto-coffee-roaster.store/policies/terms-of-service / https://www.kumamoto-coffee-roaster.store/policies/refund-policy
