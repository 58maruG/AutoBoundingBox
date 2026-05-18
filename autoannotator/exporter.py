"""アノテーションの書き出し（YOLO形式 / COCO JSON / 学習用データセット）。"""

from __future__ import annotations

import json
import os
import random
import shutil

from autoannotator.models import ClassDef, ImageItem


def _clamp01(value: float) -> float:
    """0.0〜1.0 にクランプする。"""
    return max(0.0, min(1.0, value))


def _yolo_lines(image: ImageItem) -> list[str]:
    """画像の全ボックスを YOLO形式の行（class_id cx cy w h、正規化）にする。"""
    lines: list[str] = []
    if image.width > 0 and image.height > 0:
        for box in image.boxes:
            cx = _clamp01((box.x + box.w / 2) / image.width)
            cy = _clamp01((box.y + box.h / 2) / image.height)
            nw = _clamp01(box.w / image.width)
            nh = _clamp01(box.h / image.height)
            lines.append(f"{box.class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
    return lines


def _write_txt(txt_path: str, lines: list[str]) -> None:
    """ラベル .txt を書き出す（ボックスが無くても空ファイルを作る）。"""
    with open(txt_path, "w", encoding="utf-8") as f:
        if lines:
            f.write("\n".join(lines) + "\n")


def _write_classes_txt(output_dir: str, classes: list[ClassDef]) -> None:
    with open(
        os.path.join(output_dir, "classes.txt"), "w", encoding="utf-8"
    ) as f:
        for cls in classes:
            f.write(cls.name + "\n")


def _write_data_yaml(
    output_dir: str, classes: list[ClassDef], splits: list[str]
) -> None:
    """学習用 data.yaml を書き出す。splits が空ならパス行は書かない。"""
    with open(
        os.path.join(output_dir, "data.yaml"), "w", encoding="utf-8"
    ) as f:
        f.write("# DCRsystem 自動アノテーションツールが書き出したクラス定義\n")
        if splits:
            f.write(f"path: {output_dir}\n")
            f.write("train: images/train\n")
            f.write("val: images/val\n")
            if "test" in splits:
                f.write("test: images/test\n")
        else:
            f.write("# train / val のパスは学習時に追記してください\n")
        f.write(f"nc: {len(classes)}\n")
        f.write("names:\n")
        for index, cls in enumerate(classes):
            f.write(f"  {index}: {cls.name}\n")


def export_yolo(
    images: list[ImageItem],
    classes: list[ClassDef],
    output_dir: str,
) -> None:
    """フラット形式で書き出す。

    出力:
      <output_dir>/labels/<画像名>.txt … 1行 = "class_id cx cy w h"（正規化）
      <output_dir>/classes.txt
      <output_dir>/data.yaml
    """
    labels_dir = os.path.join(output_dir, "labels")
    os.makedirs(labels_dir, exist_ok=True)

    for image in images:
        base = os.path.splitext(os.path.basename(image.path))[0]
        _write_txt(
            os.path.join(labels_dir, base + ".txt"), _yolo_lines(image)
        )

    _write_classes_txt(output_dir, classes)
    _write_data_yaml(output_dir, classes, splits=[])


def export_coco(
    images: list[ImageItem],
    classes: list[ClassDef],
    output_path: str,
) -> None:
    """COCO形式の JSON を1ファイル書き出す。

    bbox は [x, y, width, height]（画像ピクセル絶対座標）。
    category_id は 1 始まり（COCOの慣例）。
    """
    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": index + 1, "name": cls.name}
            for index, cls in enumerate(classes)
        ],
    }

    annotation_id = 1
    for image_id, image in enumerate(images, start=1):
        coco["images"].append(
            {
                "id": image_id,
                "file_name": os.path.basename(image.path),
                "width": image.width,
                "height": image.height,
            }
        )
        for box in image.boxes:
            coco["annotations"].append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": box.class_id + 1,
                    "bbox": [
                        round(box.x, 2),
                        round(box.y, 2),
                        round(box.w, 2),
                        round(box.h, 2),
                    ],
                    "area": round(box.w * box.h, 2),
                    "iscrowd": 0,
                }
            )
            annotation_id += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(coco, f, ensure_ascii=False, indent=2)


def _assign_splits(
    count: int, ratios: dict[str, float], seed: int
) -> list[str]:
    """画像数 count を ratios に従い分割し、各画像の split 名リストを返す。"""
    order = list(range(count))
    random.Random(seed).shuffle(order)

    splits = list(ratios.keys())
    result = [""] * count
    start = 0
    for i, split in enumerate(splits):
        if i == len(splits) - 1:
            end = count  # 最後の split は余りを全部受け取る
        else:
            end = start + int(round(count * ratios[split]))
        for idx in order[start:end]:
            result[idx] = split
        start = end
    return result


def export_training_dataset(
    images: list[ImageItem],
    classes: list[ClassDef],
    output_dir: str,
    ratios: dict[str, float],
    seed: int = 42,
    write_coco: bool = True,
) -> dict[str, int]:
    """学習用データセット構造で書き出す。

    出力:
      <output_dir>/images/<split>/  … 画像をコピー
      <output_dir>/labels/<split>/  … ラベル .txt
      <output_dir>/data.yaml        … 学習にそのまま使える定義
      <output_dir>/classes.txt
      <output_dir>/annotations_coco.json （write_coco=True のとき）

    ratios 例: {"train": 0.7, "val": 0.2, "test": 0.1}
    戻り値: {split名: 画像数}
    """
    splits = list(ratios.keys())
    for split in splits:
        os.makedirs(os.path.join(output_dir, "images", split), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "labels", split), exist_ok=True)

    assignment = _assign_splits(len(images), ratios, seed)
    counts = {split: 0 for split in splits}

    for image, split in zip(images, assignment):
        filename = os.path.basename(image.path)
        base = os.path.splitext(filename)[0]
        # 画像をコピー
        shutil.copy2(
            image.path, os.path.join(output_dir, "images", split, filename)
        )
        # ラベルを書き出し
        _write_txt(
            os.path.join(output_dir, "labels", split, base + ".txt"),
            _yolo_lines(image),
        )
        counts[split] += 1

    _write_classes_txt(output_dir, classes)
    _write_data_yaml(output_dir, classes, splits)
    if write_coco:
        export_coco(
            images, classes, os.path.join(output_dir, "annotations_coco.json")
        )
    return counts
