"""画像表示・アノテーション編集用キャンバス。

操作:
  - 左ドラッグ（空き領域） : 新規ボックスを描画
  - 左クリック/ドラッグ（ボックス上） : 選択・移動・リサイズ
  - 中ボタンドラッグ : パン
  - マウスホイール : ズーム
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from autoannotator.box_item import BoxItem
from autoannotator.models import BBox, ClassDef, ImageItem

# ズーム倍率の下限・上限
_MIN_SCALE = 0.05
_MAX_SCALE = 30.0
# 新規ボックスとして認める最小サイズ（シーン座標）
_MIN_DRAW = 4.0


class AnnotationCanvas(QGraphicsView):
    """画像を表示し、bbox の描画・編集を行うキャンバス。"""

    boxesChanged = Signal()      # ボックスの追加・削除が起きた
    selectionChanged = Signal()  # 選択状態が変化した
    drawBlocked = Signal()       # クラス未選択で描画できなかった

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.selectionChanged.connect(self.selectionChanged.emit)

        self._pixmap_item = None
        self._user_zoomed = False

        self._classes: list[ClassDef] = []
        self._active_class = -1
        self._image_item: ImageItem | None = None
        self._box_items: list[BoxItem] = []

        # 操作状態
        self._drawing = False
        self._draw_origin = QPointF()
        self._rubber: QGraphicsRectItem | None = None
        self._panning = False
        self._pan_start = QPointF()

        # Undo スタック（スナップショット方式、最大50件）
        self._undo_stack: list[list[BBox]] = []
        # 内部クリップボード
        self._clipboard: list[BBox] = []
        # ドラッグ開始前に保存するスナップショット（移動・リサイズ用）
        self._pre_drag_snapshot: list[BBox] | None = None

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # クラス情報
    # ------------------------------------------------------------------
    def set_classes(self, classes: list[ClassDef]) -> None:
        """クラスリスト（メインウィンドウと共有）を設定する。"""
        self._classes = classes

    def set_active_class(self, class_id: int) -> None:
        """新規ボックスに割り当てるクラスを設定する。"""
        self._active_class = class_id

    def class_info(self, class_id: int) -> tuple[str, QColor]:
        """class_id に対応する (名前, 色) を返す。BoxItem から呼ばれる。"""
        if 0 <= class_id < len(self._classes):
            cls = self._classes[class_id]
            return cls.name, QColor(cls.color)
        return "?", QColor("#888888")

    def _can_draw(self) -> bool:
        return 0 <= self._active_class < len(self._classes)

    # ------------------------------------------------------------------
    # 画像とボックスの表示
    # ------------------------------------------------------------------
    def show_image_item(self, item: ImageItem) -> bool:
        """画像と、それに紐づくボックスを表示する。成功すれば True。"""
        self._image_item = item
        self._box_items = []
        self._rubber = None
        self._drawing = False
        # 画像切り替え時は undo スタックをリセット
        self._undo_stack.clear()
        self._pre_drag_snapshot = None
        self._scene.clear()
        self._pixmap_item = None

        pixmap = QPixmap(item.path)
        if pixmap.isNull():
            self._scene.setSceneRect(0, 0, 0, 0)
            return False

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(-1)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._user_zoomed = False
        self.fit_to_window()

        for bbox in item.boxes:
            self._add_box_item(bbox)
        return True

    def clear_image(self) -> None:
        """表示中の画像とボックスをクリアする。"""
        self._image_item = None
        self._box_items = []
        self._rubber = None
        self._undo_stack.clear()
        self._pre_drag_snapshot = None
        self._scene.clear()
        self._pixmap_item = None
        self._scene.setSceneRect(0, 0, 0, 0)

    def _add_box_item(self, bbox: BBox) -> BoxItem:
        box_item = BoxItem(bbox, self.class_info)
        self._scene.addItem(box_item)
        self._box_items.append(box_item)
        return box_item

    def reload_boxes(self) -> None:
        """現在の画像のボックスを作り直す（クラス削除後などに使う）。"""
        for box_item in self._box_items:
            self._scene.removeItem(box_item)
        self._box_items = []
        # 外部からボックスリストを上書きされた場合はスタックをリセット
        self._undo_stack.clear()
        self._pre_drag_snapshot = None
        if self._image_item is None:
            return
        for bbox in self._image_item.boxes:
            self._add_box_item(bbox)

    def repaint_boxes(self) -> None:
        """全ボックスを再描画する（クラス名・色変更後に使う）。"""
        for box_item in self._box_items:
            box_item.update()

    def image_size(self) -> tuple[int, int]:
        """表示中の画像サイズ (幅, 高さ)。未表示なら (0, 0)。"""
        if self._pixmap_item is None:
            return (0, 0)
        pixmap = self._pixmap_item.pixmap()
        return (pixmap.width(), pixmap.height())

    # ------------------------------------------------------------------
    # Undo / クリップボード
    # ------------------------------------------------------------------
    def _deep_copy_boxes(self) -> list[BBox]:
        """現在の画像のボックスリストをディープコピーして返す。"""
        if self._image_item is None:
            return []
        return copy.deepcopy(self._image_item.boxes)

    def _save_snapshot(self) -> None:
        """操作前にスナップショットをスタックに積む（最大50件）。"""
        self._undo_stack.append(self._deep_copy_boxes())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _snapshots_differ(self, s1: list[BBox], s2: list[BBox]) -> bool:
        """2つのスナップショットが異なるか調べる。"""
        if len(s1) != len(s2):
            return True
        return any(
            (a.x, a.y, a.w, a.h, a.class_id) != (b.x, b.y, b.w, b.h, b.class_id)
            for a, b in zip(s1, s2)
        )

    def undo(self) -> None:
        """直前の操作を元に戻す。"""
        if not self._undo_stack or self._image_item is None:
            return
        # スタックから復元（reload_boxes はスタックをクリアするため直接再構築）
        self._image_item.boxes = self._undo_stack.pop()
        for box_item in self._box_items:
            self._scene.removeItem(box_item)
        self._box_items = []
        for bbox in self._image_item.boxes:
            self._add_box_item(bbox)
        self.boxesChanged.emit()

    def can_undo(self) -> bool:
        """Undo できる操作が残っているか。"""
        return bool(self._undo_stack)

    def copy_selected(self) -> None:
        """選択中のボックスを内部クリップボードにコピーする。"""
        self._clipboard = [
            copy.deepcopy(bi.bbox)
            for bi in self._box_items
            if bi.isSelected()
        ]

    def has_clipboard(self) -> bool:
        """クリップボードにデータがあるか。"""
        return bool(self._clipboard)

    def paste_boxes(self) -> None:
        """クリップボードのボックスを現在の画像に貼り付ける。"""
        if not self._clipboard or self._image_item is None:
            return
        self._save_snapshot()
        self._scene.clearSelection()
        bounds = self._scene.sceneRect()
        offset = 10.0
        for src in self._clipboard:
            new_box = copy.deepcopy(src)
            # 少しずらして画像内に収める
            new_box.x = min(src.x + offset, max(0.0, bounds.right() - src.w))
            new_box.y = min(src.y + offset, max(0.0, bounds.bottom() - src.h))
            new_box.confidence = None  # 貼り付けは手動ボックス扱い
            self._image_item.boxes.append(new_box)
            box_item = self._add_box_item(new_box)
            box_item.setSelected(True)
        self.boxesChanged.emit()

    # ------------------------------------------------------------------
    # 選択ボックスの操作
    # ------------------------------------------------------------------
    def has_selection(self) -> bool:
        return any(b.isSelected() for b in self._box_items)

    def delete_selected(self) -> None:
        """選択中のボックスを削除する。"""
        to_remove = [bi for bi in self._box_items if bi.isSelected()]
        if not to_remove:
            return
        self._save_snapshot()
        for box_item in to_remove:
            if self._image_item is not None:
                self._image_item.boxes = [
                    b for b in self._image_item.boxes if b is not box_item.bbox
                ]
            self._scene.removeItem(box_item)
            self._box_items.remove(box_item)
        self.boxesChanged.emit()

    def apply_class_to_selection(self, class_id: int) -> None:
        """選択中のボックスのクラスを変更する。"""
        if not (0 <= class_id < len(self._classes)):
            return
        selected = [bi for bi in self._box_items if bi.isSelected()]
        if not selected:
            return
        self._save_snapshot()
        for box_item in selected:
            box_item.bbox.class_id = class_id
            box_item.update()

    def cancel_action(self) -> None:
        """描画中の操作をキャンセルし、選択を解除する。"""
        if self._drawing:
            self._drawing = False
            self._remove_rubber()
        self._scene.clearSelection()

    # ------------------------------------------------------------------
    # ズーム・フィット
    # ------------------------------------------------------------------
    def fit_to_window(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(
                self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio
            )
            self._user_zoomed = False

    def zoom_in(self) -> None:
        self._zoom(1.25)

    def zoom_out(self) -> None:
        self._zoom(0.8)

    def _zoom(self, factor: float) -> None:
        if self._pixmap_item is None:
            return
        target = self.transform().m11() * factor
        if not (_MIN_SCALE <= target <= _MAX_SCALE):
            return
        self.scale(factor, factor)
        self._user_zoomed = True

    def wheelEvent(self, event) -> None:
        if self._pixmap_item is None:
            return
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._pixmap_item is not None and not self._user_zoomed:
            self.fit_to_window()

    # ------------------------------------------------------------------
    # マウス操作
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item:
            item = self.itemAt(event.pos())
            if isinstance(item, BoxItem):
                # ドラッグ前のスナップショットを保存（移動・リサイズの undo 用）
                self._pre_drag_snapshot = self._deep_copy_boxes()
                super().mousePressEvent(event)
                return
            # 空き領域 → 新規ボックスの描画開始
            if not self._can_draw():
                self.drawBlocked.emit()
                return
            self._scene.clearSelection()
            self._drawing = True
            self._draw_origin = self._clamp_point(self.mapToScene(event.pos()))
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - int(delta.x()))
            v_bar.setValue(v_bar.value() - int(delta.y()))
            event.accept()
            return

        if self._drawing:
            current = self._clamp_point(self.mapToScene(event.pos()))
            self._update_rubber(
                QRectF(self._draw_origin, current).normalized()
            )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self._drawing and event.button() == Qt.MouseButton.LeftButton:
            self._drawing = False
            current = self._clamp_point(self.mapToScene(event.pos()))
            rect = QRectF(self._draw_origin, current).normalized()
            self._remove_rubber()
            if rect.width() >= _MIN_DRAW and rect.height() >= _MIN_DRAW:
                self._create_box(rect)
            event.accept()
            return

        # ボックスのドラッグ（移動・リサイズ）終了: 変化があれば undo に積む
        if event.button() == Qt.MouseButton.LeftButton:
            if self._pre_drag_snapshot is not None:
                current_state = self._deep_copy_boxes()
                if self._snapshots_differ(self._pre_drag_snapshot, current_state):
                    self._undo_stack.append(self._pre_drag_snapshot)
                    if len(self._undo_stack) > 50:
                        self._undo_stack.pop(0)
                self._pre_drag_snapshot = None

        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------
    def _clamp_point(self, point: QPointF) -> QPointF:
        """点を画像領域内にクランプする。"""
        rect = self._scene.sceneRect()
        x = min(max(point.x(), rect.left()), rect.right())
        y = min(max(point.y(), rect.top()), rect.bottom())
        return QPointF(x, y)

    def _create_box(self, rect: QRectF) -> None:
        if self._image_item is None:
            return
        self._save_snapshot()
        bbox = BBox(
            class_id=self._active_class,
            x=rect.x(),
            y=rect.y(),
            w=rect.width(),
            h=rect.height(),
        )
        self._image_item.boxes.append(bbox)
        box_item = self._add_box_item(bbox)
        self._scene.clearSelection()
        box_item.setSelected(True)
        self.boxesChanged.emit()

    def _update_rubber(self, rect: QRectF) -> None:
        if self._rubber is None:
            self._rubber = QGraphicsRectItem()
            pen = QPen(QColor("#00d9ff"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._rubber.setPen(pen)
            self._rubber.setBrush(QColor(0, 217, 255, 40))
            self._rubber.setZValue(1000)
            self._scene.addItem(self._rubber)
        self._rubber.setRect(rect)

    def _remove_rubber(self) -> None:
        if self._rubber is not None:
            self._scene.removeItem(self._rubber)
            self._rubber = None
