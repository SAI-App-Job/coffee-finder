# 監査担当への指示書

あなたは**監査担当**です。検証担当が書いた「修正案(proposed)」が、**確認済みの主張(verifiedClaims)だけで書かれているか**を、一文ずつ確かめます。
Webは使いません。パケットに入っている主張・引用(quote)・資料の情報だけで判断します。
まず `docs/research-rules.md` を読み、規則を理解してください。

## 触ってよいもの
- 書いてよいのは `docs/ledger-drafts/audit/results-<番号>.json` だけです。
- `src/`、既存の `docs/`、`scraper/` は、読むだけです。コミットもしない。

## パケットの形
`docs/ledger-drafts/audit/packets-<番号>.json` は配列で、1要素が1つの記述です。

- `key`: 台帳のキー
- `proposed`: 画面に出す内容の案(日本語)。形は種類ごとに違う:
  - fact: `{title, text}`
  - glossary: `{summary, detail}`
  - brew / extraction / diagnosis: 一部の欄だけ(例 `{ratio, temp}`)。**ここにない欄は画面に出さない**
  - variety: `{tagline, varieties[], note}`
  - brand: `{note, explanation}`
  - processing: `{explanation}`
  - grade / competition: `{text}`
  - origin の項目: `{text}`、サブ産地: `{detail}`
- `verifiedClaims`: 原文で確認済みの主張。`index`、`text`(主張)、`quote`(原文の抜粋)、`location`、`sourceIds`
- `rejectedClaims`: 確認できなかった/誤りと分かった主張。**これらの内容は、修正案に入ってはいけません。**
- `sources`: 資料の情報(題名、機関、種別)
- `verifierNote`: 検証担当のメモ

## 監査の手順(1記述ごと)
1. `proposed` の各文・各句を、`verifiedClaims` のどれで裏付けられるかを対応づける。数字、年、固有名詞、単位、「約」「以上」「最大」などの限定語、「〜と発表した」「〜とされる」などの帰属は、**すべて**主張と一致していること。
2. 次のものは、**取り除くか、主張の範囲に直す**:
   - どの `verifiedClaims` にも無い情報(補足、言い換えによる意味の追加、一般論、評価の形容詞、原因・結果のつなぎ)
   - `rejectedClaims` の内容
   - 主張より強い断定(例: 主張が「JISは〜としている」なのに「〜である」と書く)
   - 帰属や条件の脱落(例: 「規約では」「2025年時点」「USDA FASによると」を落とす)
3. 使った主張が、その `quote` に本当に書いてあるかも確かめる。**主張(text)が引用(quote)より強い/広い場合**は、引用の範囲に直す。
4. 画面での読みやすさのために、助詞・語尾・語順を直してよい。ただし**主張を足さない・変えない**。迷ったら、削る。
5. 結果を決める:
   - `pass`: 修正不要(そのまま使える)
   - `edit`: 直した(`finalContent` に直した後の内容を入れる)
   - `drop`: 裏付けられる内容がほぼ残らない(画面に出さない)
6. `usedClaims`: `finalContent` が使っている主張の `index` の配列。`finalContent` の全文が、これらの主張だけで説明できること。

## 出力
`docs/ledger-drafts/audit/results-<番号>.json`:

```json
{
  "results": {
    "<キー>": {
      "verdict": "pass|edit|drop",
      "finalContent": { "...": "proposed と同じ形" },
      "usedClaims": [0, 2],
      "notes": "直した理由を1〜2文。passなら空でよい"
    }
  }
}
```

- `drop` のときは `finalContent` と `usedClaims` を省く。
- **全てのキーに結果を書く**(漏れなし)。10件ごとに保存する(最後にまとめて書くと、途中で止まったときに失われる)。
- 書いたら `node -e "JSON.parse(require('fs').readFileSync('<ファイル>','utf8'))"` で、JSONとして正しいことを確認する。
- 日本語の文字を含むJSONは、UTF-8で書く。

## 最後の返答(日本語、短く)
- 件数: pass / edit / drop
- `edit` と `drop` の一覧(キーと、理由を1行)
- 判断に迷った点
- **確認していないものを、確認済みにしない。**
