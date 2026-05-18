"""アプリ全体で共有するデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 取り込み対象とする画像拡張子（小文字で比較する）
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


@dataclass
class ClassDef:
    """アノテーションのクラス定義。

    class_id はクラスリスト内の並び順（インデックス）で決まる。
    color は "#RRGGBB" 形式の文字列。
    """

    name: str
    color: str


# 既定クラス（YOLO学習パイプラインの yolo_SusHi.yaml と同じ並び順）
_DEFAULT_CLASS_SPECS = (
    ("birddamage", "#87ceeb"),  # 空色
    ("healthy", "#ffffff"),     # 白
    ("mold", "#9c27b0"),        # 紫
    ("stemcrack", "#2962ff"),   # 青
    ("twin", "#e6194b"),        # 赤
    ("unripe", "#ffd500"),      # 黄色
)


def default_classes() -> list[ClassDef]:
    """既定クラス一覧を新しいインスタンスのリストで返す。"""
    return [ClassDef(name, color) for name, color in _DEFAULT_CLASS_SPECS]


@dataclass
class BBox:
    """バウンディングボックス1個。

    座標は画像ピクセル単位（左上を原点とする x, y と幅 w, 高さ h）。
    confidence は自動推論で付与されたボックスのみ値を持ち、
    手動で作成したボックスは None とする。
    """

    class_id: int
    x: float
    y: float
    w: float
    h: float
    confidence: float | None = None

    @property
    def x2(self) -> float:
        """右下の x 座標。"""
        return self.x + self.w

    @property
    def y2(self) -> float:
        """右下の y 座標。"""
        return self.y + self.h


@dataclass
class ImageItem:
    """1枚の画像と、それに紐づくアノテーション。"""

    path: str
    width: int = 0
    height: int = 0
    boxes: list[BBox] = field(default_factory=list)
    reviewed: bool = False  # ユーザーが目視確認済みかどうか
