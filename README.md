# A2B 自動アノテーションツール

YOLO 学習用データセットを効率よく作成するための、デスクトップ向け画像アノテーションツールです。手動でのバウンディングボックス描画に加え、学習済み YOLO モデルによる自動推論でアノテーション作業を補助します。

## 主な機能

### 画像の取り込み・閲覧
- フォルダ単位での画像読み込み（`.jpg` / `.jpeg` / `.png` / `.bmp`）
- 画像一覧からの選択、`A` / `D` キーによる前後移動
- ズーム（マウスホイール / `Ctrl +` / `Ctrl -`）、全体表示（`Ctrl 0`）、中ボタンドラッグでパン

### アノテーション編集
- 空き領域を左ドラッグして新規ボックスを描画
- ボックスの選択・移動・リサイズ
- コピー / 貼り付け、削除、最大 50 件までの「元に戻す（Undo）」
- 数字キー `1`〜`9` でクラスを切り替え、選択中ボックスへ即時適用
- `Esc` で描画操作のキャンセル・選択解除

### クラス管理
- 既定で 6 クラス（`birddamage` / `healthy` / `mold` / `stemcrack` / `twin` / `unripe`）を用意
- クラスの追加・名称変更・色変更・削除に対応
- クラス削除時は全画像のボックスのクラス ID を自動で振り直し

### YOLO モデルによる自動推論
- `.pt` 形式の学習済み YOLO モデルを読み込み
- 現在表示中の 1 枚、または未アノテーションの全画像をまとめて推論
- バッチ推論はバックグラウンドスレッドで実行し、進捗表示・途中キャンセルに対応
- 信頼度（confidence）のしきい値を指定可能
- モデルが出力した未登録クラスは自動でクラスへ追加

### 集計・フィルター
- クラスごとのボックス数を集計表示
- クラス別の絞り込み、複数ボックスを持つ画像のみの絞り込み

### 書き出し
以下の形式でアノテーションを書き出せます。

| 形式 | 出力内容 |
| --- | --- |
| フラット | `labels/*.txt`（YOLO 形式・正規化座標）、`classes.txt`、`data.yaml` |
| 学習用データセット（train / val） | `images/<split>/`、`labels/<split>/`、`data.yaml` |
| 学習用データセット（train / val / test） | 上記に `test` split を追加 |

- 分割比率・シャッフル用 seed を指定可能
- 任意で COCO 形式の JSON（`annotations_coco.json`）も同時出力

## 動作環境

- Python 3.11 以上
- 主な依存パッケージ
  - PySide6（GUI）
  - ultralytics（YOLO 推論）
  - torch / torchvision（CUDA 12.8 ビルド・GPU 推論対応）

## セットアップ・実行

[uv](https://docs.astral.sh/uv/) を使用します。

```bash
# 依存関係のインストール
uv sync

# アプリの起動
uv run python main.py
```

## .exe ビルド（Windows）

PyInstaller を使って単体実行可能な `.exe` を生成できます。

```bash
build.bat
```

ビルド成果物は `dist\A2B\A2B.exe` に出力されます。

推論依存（torch / ultralytics）が正しく同梱されているかは、診断モードで確認できます。

```bash
A2B.exe --selftest
```

実行ファイルと同じ場所に `selftest_result.json` が出力されます。

## 基本的な使い方

1. 「画像フォルダを開く」で対象画像のフォルダを読み込む
2. （任意）「モデル選択 (.pt)」で学習済み YOLO モデルを読み込み、「現在の画像を推論」または「全画像を推論」で自動アノテーション
3. キャンバス上でボックスを描画・修正し、クラスを割り当てる
4. 「アノテーションを書き出す」で形式・分割比率を選び、出力先フォルダを指定

## プロジェクト構成

```
A2B/
├── main.py                  エントリポイント（--selftest 診断モード含む）
├── autoannotator/
│   ├── main_window.py       メインウィンドウ・全体制御
│   ├── canvas.py            画像表示・ボックス編集キャンバス
│   ├── box_item.py          バウンディングボックスの描画アイテム
│   ├── class_panel.py       クラス管理パネル
│   ├── inference.py         YOLO モデルの読み込み・推論
│   ├── inference_panel.py   推論操作パネル
│   ├── result_panel.py      集計・フィルターパネル
│   ├── export_dialog.py     書き出し設定ダイアログ
│   ├── exporter.py          YOLO / COCO / 学習用データセット書き出し
│   └── models.py            共有データモデル（ClassDef / BBox / ImageItem）
├── A2B.spec                 PyInstaller ビルド定義
└── build.bat                .exe ビルド用バッチ
```
