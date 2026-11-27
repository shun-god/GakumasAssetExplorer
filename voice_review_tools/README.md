# 音声確認ツール

リポジトリ直下で以下を実行して http://127.0.0.1:8765 を開きます。

```powershell
cd C:\Users\myuser\Downloads\GkmasObjectManager
uv run .\voice_review_tools\voice_review_app.py
```

入力はこのフォルダーの voice_review.sqlite3 に自動保存され、画面からCSVに書き出せます。元の音声や字幕CSVは変更しません。
アプリの5秒以上／3秒以上は下限のみで上限はありません。

- voice_review_app.py: 再生と手入力
- voice_caption_review.csv: アプリ用の確認一覧
- voice_caption_review_3s_plus.csv / voice_caption_review_5s_plus.csv: 長さ別の一覧（上限なし）
- caption_candidates.csv / caption_candidates.errors.json: シナリオの候補文と収集時のエラー
- export_character_voices.py: 音声取得
- find_caption_candidates.py: シナリオの候補文検索
- join_caption_candidates.py: 候補と音声一覧の結合
- filter_review_by_duration.py: 長さによる一覧作成
- compare_voice_captions.py: 音声認識を使う実験用（手入力には不要）

候補文は場面の表示文であり、発話と一致するとは限りません。
