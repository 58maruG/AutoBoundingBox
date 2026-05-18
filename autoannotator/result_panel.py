"""自動アノテーション結果のクラス別集計・画像フィルターパネル。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from autoannotator.models import ClassDef, ImageItem


class ResultPanel(QWidget):
    """クラス別の個数を表示し、画像一覧の絞り込みを操作するパネル。"""

    classFilterRequested = Signal(int)   # クラスIDで絞り込み
    allFilterRequested = Signal()        # 全表示に戻す
    multiBboxFilterRequested = Signal()  # bbox 2個以上の画像のみ

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 現在のフィルター状態
        self._status = QLabel("表示中: すべて")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-weight: bold; padding: 2px;")
        layout.addWidget(self._status)

        # --- クラス別の結果 ---
        class_box = QGroupBox("クラス別の結果（クリックで絞り込み）")
        class_layout = QVBoxLayout(class_box)
        self._class_list = QListWidget()
        self._class_list.setIconSize(QPixmap(14, 14).size())
        self._class_list.itemClicked.connect(self._on_class_clicked)
        class_layout.addWidget(self._class_list)
        self._btn_all = QPushButton("全てのクラスを表示")
        self._btn_all.clicked.connect(self.allFilterRequested.emit)
        class_layout.addWidget(self._btn_all)
        layout.addWidget(class_box, 1)

        # --- 複数bboxの画像 ---
        multi_box = QGroupBox("複数bboxの画像")
        multi_layout = QVBoxLayout(multi_box)
        hint = QLabel("bboxが2個以上ある画像だけを参照します。")
        hint.setWordWrap(True)
        multi_layout.addWidget(hint)
        self._btn_multi = QPushButton("複数bbox画像のみ表示")
        self._btn_multi.clicked.connect(self.multiBboxFilterRequested.emit)
        multi_layout.addWidget(self._btn_multi)
        layout.addWidget(multi_box)

    # ------------------------------------------------------------------
    def refresh(
        self, classes: list[ClassDef], images: list[ImageItem]
    ) -> None:
        """クラス別個数と複数bbox画像数を再計算して表示を更新する。"""
        box_counts: dict[int, int] = {}
        for image in images:
            for box in image.boxes:
                box_counts[box.class_id] = box_counts.get(box.class_id, 0) + 1

        # 選択状態（＝絞り込み中のクラス）を保持したまま作り直す
        selected_cid = self._selected_class_id()
        self._class_list.blockSignals(True)
        self._class_list.clear()
        for cid, cls in enumerate(classes):
            count = box_counts.get(cid, 0)
            item = QListWidgetItem(f"{cls.name}　{count} 個")
            pixmap = QPixmap(14, 14)
            pixmap.fill(QColor(cls.color))
            item.setIcon(QIcon(pixmap))
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self._class_list.addItem(item)
            if cid == selected_cid:
                item.setSelected(True)
        self._class_list.blockSignals(False)

        multi = sum(1 for img in images if len(img.boxes) >= 2)
        self._btn_multi.setText(f"複数bbox画像のみ表示（{multi} 枚）")
        self._btn_multi.setEnabled(multi > 0)

    def set_status(self, text: str) -> None:
        """現在のフィルター状態の表示を更新する。"""
        self._status.setText(text)

    def clear_class_selection(self) -> None:
        """クラスリストの選択（絞り込みハイライト）を解除する。"""
        self._class_list.clearSelection()

    # ------------------------------------------------------------------
    def _selected_class_id(self) -> int:
        items = self._class_list.selectedItems()
        if items:
            cid = items[0].data(Qt.ItemDataRole.UserRole)
            if cid is not None:
                return int(cid)
        return -1

    def _on_class_clicked(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid is not None:
            self.classFilterRequested.emit(int(cid))
