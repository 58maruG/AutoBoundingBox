"""バウンディングボックスを表す QGraphicsItem。

BoxItem は対応する BBox を直接更新する（移動・リサイズ結果がそのまま
BBox に反映される）。クラス名・色は外部から渡された class_info コールバックで
取得するため、クラスのリネーム・色変更は再描画のみで反映される。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem

from autoannotator.models import BBox

HANDLE_SIZE = 9.0  # リサイズハンドルの一辺（シーン座標）
_MIN_BOX = 4.0     # ボックスの最小サイズ

# ハンドル番号 → カーソル形状
#   0:左上 1:上 2:右上 3:右 4:右下 5:下 6:左下 7:左
_HANDLE_CURSORS = {
    0: Qt.CursorShape.SizeFDiagCursor,
    1: Qt.CursorShape.SizeVerCursor,
    2: Qt.CursorShape.SizeBDiagCursor,
    3: Qt.CursorShape.SizeHorCursor,
    4: Qt.CursorShape.SizeFDiagCursor,
    5: Qt.CursorShape.SizeVerCursor,
    6: Qt.CursorShape.SizeBDiagCursor,
    7: Qt.CursorShape.SizeHorCursor,
}


def _label_text_color(background: QColor) -> QColor:
    """ラベル背景色に対して読みやすい文字色（黒 or 白）を返す。"""
    # 知覚的な明るさ（0-255）。明るい背景は黒字、暗い背景は白字。
    luminance = (
        0.299 * background.red()
        + 0.587 * background.green()
        + 0.114 * background.blue()
    )
    return QColor("black") if luminance > 140 else QColor("white")


class BoxItem(QGraphicsItem):
    """1個のバウンディングボックス。"""

    def __init__(
        self,
        bbox: BBox,
        class_info: Callable[[int], tuple[str, QColor]],
    ) -> None:
        super().__init__()
        self.bbox = bbox
        self._class_info = class_info  # class_id -> (名前, 色)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self._mode: str | None = None  # None / "move" / "resize"
        self._handle = -1
        self._press_scene = QPointF()
        self._press_rect = QRectF()

    # ------------------------------------------------------------------
    # 幾何
    # ------------------------------------------------------------------
    def rect(self) -> QRectF:
        """ボックスの矩形（シーン座標）。"""
        return QRectF(self.bbox.x, self.bbox.y, self.bbox.w, self.bbox.h)

    def boundingRect(self) -> QRectF:
        margin = HANDLE_SIZE / 2 + 2
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def _handle_points(self) -> list[QPointF]:
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        return [
            QPointF(r.left(), r.top()),
            QPointF(cx, r.top()),
            QPointF(r.right(), r.top()),
            QPointF(r.right(), cy),
            QPointF(r.right(), r.bottom()),
            QPointF(cx, r.bottom()),
            QPointF(r.left(), r.bottom()),
            QPointF(r.left(), cy),
        ]

    def _handle_at(self, pos: QPointF) -> int:
        """指定位置にあるハンドル番号を返す。無ければ -1。"""
        tol = HANDLE_SIZE / 2 + 1
        for i, p in enumerate(self._handle_points()):
            if abs(pos.x() - p.x()) <= tol and abs(pos.y() - p.y()) <= tol:
                return i
        return -1

    def _bounds(self) -> QRectF:
        """ボックスを収める境界（＝画像領域）。"""
        if self.scene() is not None:
            return self.scene().sceneRect()
        return self.rect()

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def paint(self, painter, option, widget=None) -> None:
        painter.setClipRect(self.boundingRect())
        name, color = self._class_info(self.bbox.class_id)
        r = self.rect()
        selected = self.isSelected()

        # 枠と半透明の塗り
        fill = QColor(color)
        fill.setAlpha(55)
        painter.setBrush(fill)
        pen = QPen(color, 3 if selected else 2)
        pen.setCosmetic(True)  # ズーム倍率に依存しない線幅
        painter.setPen(pen)
        painter.drawRect(r)

        # クラス名ラベル（自動推論ボックスは信頼度も表示）
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        conf = self.bbox.confidence
        text = name if conf is None else f"{name} {conf:.2f}"
        metrics = painter.fontMetrics()
        label = QRectF(
            r.left(),
            r.top(),
            metrics.horizontalAdvance(text) + 8,
            metrics.height() + 4,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRect(label)
        painter.setPen(_label_text_color(color))
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, text)

        # 選択中はリサイズハンドルを表示
        if selected:
            painter.setPen(QPen(QColor("#222222"), 1))
            painter.setBrush(QColor("white"))
            for p in self._handle_points():
                painter.drawRect(
                    QRectF(
                        p.x() - HANDLE_SIZE / 2,
                        p.y() - HANDLE_SIZE / 2,
                        HANDLE_SIZE,
                        HANDLE_SIZE,
                    )
                )

    # ------------------------------------------------------------------
    # マウス操作
    # ------------------------------------------------------------------
    def hoverMoveEvent(self, event) -> None:
        handle = self._handle_at(event.pos())
        if handle >= 0:
            self.setCursor(_HANDLE_CURSORS[handle])
        elif self.rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self.scene() is not None:
            self.scene().clearSelection()
        self.setSelected(True)
        self._handle = self._handle_at(event.pos())
        self._mode = "resize" if self._handle >= 0 else "move"
        self._press_scene = event.scenePos()
        self._press_rect = self.rect()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._mode is None:
            return
        delta = event.scenePos() - self._press_scene
        if self._mode == "move":
            new_rect = self._clamp_move(
                self._press_rect.translated(delta.x(), delta.y())
            )
        else:
            new_rect = self._resize_rect(self._press_rect, self._handle, delta)

        self.prepareGeometryChange()
        self.bbox.x = new_rect.x()
        self.bbox.y = new_rect.y()
        self.bbox.w = new_rect.width()
        self.bbox.h = new_rect.height()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._mode = None
        self._handle = -1
        event.accept()

    # ------------------------------------------------------------------
    # 移動・リサイズの計算（画像境界にクランプ）
    # ------------------------------------------------------------------
    def _clamp_move(self, rect: QRectF) -> QRectF:
        bounds = self._bounds()
        r = QRectF(rect)
        if r.left() < bounds.left():
            r.moveLeft(bounds.left())
        if r.top() < bounds.top():
            r.moveTop(bounds.top())
        if r.right() > bounds.right():
            r.moveRight(bounds.right())
        if r.bottom() > bounds.bottom():
            r.moveBottom(bounds.bottom())
        return r

    def _resize_rect(self, base: QRectF, handle: int, delta: QPointF) -> QRectF:
        bounds = self._bounds()
        left, top = base.left(), base.top()
        right, bottom = base.right(), base.bottom()
        dx, dy = delta.x(), delta.y()

        if handle in (0, 6, 7):  # 左辺
            left = min(max(left + dx, bounds.left()), right - _MIN_BOX)
        if handle in (2, 3, 4):  # 右辺
            right = max(min(right + dx, bounds.right()), left + _MIN_BOX)
        if handle in (0, 1, 2):  # 上辺
            top = min(max(top + dy, bounds.top()), bottom - _MIN_BOX)
        if handle in (4, 5, 6):  # 下辺
            bottom = max(min(bottom + dy, bounds.bottom()), top + _MIN_BOX)

        return QRectF(QPointF(left, top), QPointF(right, bottom))

    # ------------------------------------------------------------------
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)
