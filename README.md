# GakumasAssetExplorer

『学園アイドルマスター』の画像・音声・動画などのアセットを、ブラウザーや Python から探して取得するツールです。キャラクターのボイスと台詞をまとめて書き出すこともできます。

- このリポジトリは [shun-god/GakumasAssetExplorer](https://github.com/shun-god/GakumasAssetExplorer) です。
- AllenHeartcore 氏の [GkmasObjectManager](https://github.com/AllenHeartcore/GkmasObjectManager) を取得し、そこから開発を続けています。Python から使うときのモジュール名は `GkmasObjectManager` です。

## セットアップ

[uv](https://docs.astral.sh/uv/getting-started/installation/) をインストールし、以下を実行します。すでにリポジトリを取得済みなら、そのフォルダで `uv sync --locked` を実行してください。

```sh
git clone https://github.com/shun-god/GakumasAssetExplorer.git
cd GakumasAssetExplorer
uv sync --locked
```

既定の Python は 3.12 です。依存ライブラリは `uv.lock` に記録されたバージョンで `.venv` にインストールされます。動画変換などで FFmpeg を使う場合は、別途インストールして `PATH` に追加してください。

## Web UI でアセットを探す

```sh
uv run --locked python server.py
```

ブラウザーで [http://127.0.0.1:5001](http://127.0.0.1:5001) を開きます。検索欄に `shro` や `sud_vo_adv` など、アセット名の一部を入力すると候補を探せます。検索結果から詳細ページを開くと、対応するアセットをプレビュー・ダウンロードできます。

## キャラクターの音声と台詞を書き出す

キャラクター ID を指定して実行します。たとえば `shro` は篠澤 広です。指定できる ID は [CHARACTER_ABBREVS](GkmasObjectManager/const.py) または `uv run --locked python export_voices.py --help` で確認できます。

```sh
uv run --locked python export_voices.py shro -o shro_voices
```

複数人を指定すると、同じシナリオの音声を一度だけ取得・デコードして、話者ごとに振り分けます。この例では `voices` の下に `shro_voices`、`hski_voices`、`ttmr_voices` ができます。

```sh
uv run --locked python export_voices.py shro hski ttmr -o voices
```

`-o` は、単体指定ならキャラクターの出力先、複数指定ならキャラクター別フォルダをまとめる親フォルダです。省略すると、現在のディレクトリに `<キャラクターID>_voices` が作られます。

各アーカイブのフォルダに WAV と `captions.csv` が入ります。シナリオ音声はトラック名で話者を判定するため、ほかのキャラクターのシナリオに登場する台詞も対象です。

| CSV の `caption_status` | 意味 |
| --- | --- |
| `matched` | 音声に対応する台詞が見つかった |
| `not_found` | シナリオ音声に対応する台詞が見つからなかった |
| `not_applicable` | システムボイスなど、台詞の照合対象外の音声 |

再実行すると、キャラクターごとの `.completed.json` を参照して処理済みのアーカイブをスキップします。出力先を引き継いだまま、対象キャラクターを追加できます。

まず 1 件だけ試したい場合は `--archive` でアーカイブ名を指定します。

```sh
uv run --locked python export_voices.py shro --archive "sud_vo_adv_dear_shro_001.acb"
```

保存済みのマニフェストを使う場合は `--manifest <ファイルのパス>` を指定します。

## 音声と台詞を聴き比べる（Windows）

[`voice_viewer/launch.cmd`](voice_viewer/launch.cmd) をエクスプローラーでダブルクリックすると、既定のブラウザーでビューアーが開きます。ターミナルからは `uv run --locked python voice_viewer/viewer.py` で起動できます。

1. リポジトリ直下の `shro_voices` を自動で開きます。別の場所の音声は「音声フォルダ」にパスを入力して「開く」を押します。複数キャラクターをまとめた親フォルダも指定できます。
2. 台詞やファイル名で検索できます。「未検出台詞を隠す」を選ぶと、台詞が見つからなかったシナリオ音声を一覧から除外できます。一覧の「長さ（秒）」を確認し、並べ替えで短い順・長い順に切り替えられます。「再生」を押すか行をダブルクリックすると WAV が流れます。
3. 聴き比べたい行をそれぞれ「A に登録」「B に登録」し、「A を再生」「B を再生」で切り替えます。登録した音声は別のフォルダを開いた後も再生できます。

ビューアーは `voice_viewer/` の独立した Flask アプリとして動作し、WAV と `captions.csv` をローカルで読み込みます。終了するには起動時のコンソールで Ctrl+C を押します。

## Python から使う

`uv run --locked python` で対話シェルを起動し、次のように使えます。マニフェストはゲーム内アセットの一覧です。

```python
import GkmasObjectManager as gom

manifest = gom.fetch()
manifest.export("manifest.json")

# カード画像の名前を検索する
for asset in manifest.search(r"img.*cidol.*full.*")[:5]:
    print(asset.name)

# カード画像を JPEG で保存する
manifest.download(
    r"img.*cidol.*full.*",
    path="card_images",
    image_format="jpeg",
)
```

`gom.load()` で保存済みのマニフェストを読み込み、新旧の差分を確認できます。クラス構成、アセット名のパターン、プリセットの使用例は [派生元の README](https://github.com/AllenHeartcore/GkmasObjectManager#readme) を参照してください。

## 依存ライブラリを変更する

`uv add <パッケージ名>` で追加し、`uv remove <パッケージ名>` で削除します。依存関係を変更したら `pyproject.toml` と `uv.lock` を一緒にコミットしてください。

## クレジットとライセンス

- 派生元の GkmasObjectManager は [Ziyuan "Heartcore" Chen](https://allenheartcore.github.io/) 氏が開発しました。
- GkmasObjectManager は Kishida Natsumi 氏の [gkmasToolkit](https://github.com/kishidanatsumi/gkmasToolkit) を改修したものです。gkmasToolkit は Vibbit 氏の [HoshimiToolkit](https://github.com/MalitsPlus/HoshimiToolkit) をもとにしています。
- 配信 API へのリクエストと復号処理は、DreamGallery 氏の [HatsuboshiToolkit](https://github.com/DreamGallery/HatsuboshiToolkit) に由来します。

ソースコードのライセンスは [GNU GPL v3](LICENSE) です。
