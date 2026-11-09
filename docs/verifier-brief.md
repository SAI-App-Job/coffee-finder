# 検証担当への指示書

あなたは**検証担当**です。アプリに載っている記述が、公式の一次資料の原文と合っているかを、1つずつ確かめます。
まず `docs/research-rules.md` を最後まで読み、その規則にすべて従ってください。この指示書は、その具体的な手順です。

## 立場
- あなたは、記述を書いた人とは別の担当です。**書かれた内容を信じないでください。** 原文を自分で取り直して確かめます。
- 目的は「記述を残すこと」ではなく、「根拠のある記述だけを残すこと」です。根拠が取れない主張は、遠慮なく `unverified` にしてください。

## 触ってよいもの・いけないもの
- **書いてよいのは `docs/ledger-drafts/<あなたの範囲>.json` だけ**です。
- `src/`、`docs/` の既存ファイル、`scraper/`、`data/` は、読むだけで編集しない。コミットもしない。
- `docs/*.md` の調査資料は、**手がかりとして読むのは良いが、根拠にはならない**(孫引き禁止)。

## 手順
1. 範囲のデータを読む(日本語が正)。英訳が `src/data/en/` にある場合は、日本語と同じ主張かも見る(食い違いは `note` に)。
2. 各記述(キーは `docs/research-rules.md` の表)を、**事実1つごとの主張**に分ける。固有名詞、数字、年、標高、法令名、順位、因果関係を、それぞれ別の主張にする。
3. 各主張について、**公式の一次資料**を探す。
   - 各国政府・各国のコーヒー機関・規格機関・協会の公式サイトと公式文書を最優先にする。現地語(スペイン語、ポルトガル語、インドネシア語、ベトナム語、アムハラ語の公式英語版など)でも探す。複数の検索語、機関名、サイト指定(`allowed_domains`)を試す。
   - 国際機関の公式文書(ICO、SCA、WCR、WCE、USDA FAS、FAO、各国の統計局など)も使う。
   - 報道・業界紙・小売店・Wikipedia・ブログは、手がかりにしてよいが、根拠にしない。
4. **原文を取得して読む。**
   - PDF: `curl -sL -o <ファイル> "<URL>"` で保存し、`python -I -c "import pypdf; ..."` で本文を抽出して読む(`pypdf`は入っている)。
   - HTML: `curl -sL "<URL>"` で生のHTMLを取得し、`python -I` で本文を取り出して読む。curlが通らないときだけ、ページ取得ツール(WebFetch)を使う。
   - **ページ取得ツールの返答は要約であり、引用ではない。** `quote` には、curl/pypdfで取り出した生の本文からそのままの文をコピーする。ツールの要約から`quote`を作らない。
   - 403、接続エラー、本文が空のときは、`sources` に `readMethod: "failed"` で記録する(別の資料で代用して済ませない)。
5. 主張を判定する。
   - `verified`: **`kind: "primary"` かつ `readMethod: "full-text"`** の資料の原文と一致した。`quote`と`location`(条項・ページ・見出し)を必ず書く。
   - `incorrect`: 原文と食い違う。正しい内容と、その原文の`quote`を書く。
   - `conflict`: 公式資料どうしが食い違う。両方の`quote`を`note`に書く。**あなたが解決しない**(ユーザーが決める)。
   - `unverified`: 公式の一次資料の原文では確認できない。報道などの二次資料にしか見つからないときも`unverified`にして、`note`に「二次資料のみ: <sourceId>」と書く(二次資料を`sourceIds`に入れてよい)。
6. 記述の`status`は、全主張が`verified`のときだけ`verified`。それ以外は`partial`(一部が`verified`)か`unverified`。
7. 全主張が`verified`でない記述には、`suggestedText`(日本語)を書く: **`verified`の主張だけ**で読める自然な文に直したもの。`incorrect`は、原文に基づく正しい内容に直す。言葉を足さない。主張を足さない。全主張が`verified`なら不要。
8. 数字・年・名前は、原文のとおりに写す。丸めない。

## 出力
`docs/ledger-drafts/<範囲>.json`:

```json
{
  "scope": "範囲の名前",
  "verifiedOn": "2026-11-08",
  "sources": { "<id>": { "title": "", "org": "", "url": "", "kind": "primary|secondary", "readMethod": "full-text|excerpt|snippet|failed", "accessed": "2026-11-08", "note": "" } },
  "entries": {
    "<キー>": {
      "status": "verified|partial|unverified",
      "claims": [ { "text": "", "status": "verified|unverified|incorrect|conflict", "sourceIds": [], "quote": "", "location": "", "note": "" } ],
      "suggestedText": "",
      "note": ""
    }
  }
}
```

- 書いたら `node -e "JSON.parse(require('fs').readFileSync('<ファイル>','utf8'))"` で、JSONとして正しいことを確認する。
- `quote`が空の`verified`は不可。`sourceIds`が空の`verified`も不可。

## 最後の返答(日本語、短く)
- 記述数と、`verified` / `partial` / `unverified` の件数
- `incorrect`(アプリの記述が誤り)と`conflict`(資料どうしの食い違い)の一覧。1行ずつ、記述のキー・内容・根拠のURL
- 取得に失敗した資料(`failed`)
- 時間が足りず、手を付けられなかった記述(あれば)。**確認していないものを確認済みにしない。**
