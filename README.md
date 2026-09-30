# venutrip-x-auto

VENUTRIPのX自動投稿システムです。毎日6:30（JST）に公開情報を調査し、Buffer経由で8:00、10:00、12:00、17:00、19:00の5投稿を予約します。

- 各投稿は画像1枚。Pexelsの実写を優先し、見つからない場合だけAI画像で補います。
- 実写はAI注記なし、AI画像の場合は「※画像はAI生成イメージ」を付けます。
- Bufferへ送る直前に、全投稿末尾へ正式URLを必ず付与します。

```text
▼VENUTRIPで周辺情報をチェック
https://venutrip.jp
```

GitHub Repository Variable `VENUTRIP_SITE_URL` は `https://venutrip.jp` に設定します。未設定時も同URLを使用します。Pexels利用時は Repository Secret `PEXELS_API_KEY` が必要で、未設定・取得失敗時はAI画像へ安全にフォールバックします。
