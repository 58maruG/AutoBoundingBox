"""クラス（ラベル種類）管理パネル。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from autoannotator.models import ClassDef

# 新規クラスに順番に割り当てる配色
_PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
    "#dcbeff", "#9a6324", "#800000", "#808000", "#000075",
]


def _make_swatch(color_hex: str, size: int = 16) -> QIcon:
    """クラス色を表す四角アイコンを生成する。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color_hex))
    return QIcon(pixmap)


class ClassPanel(QWidget):
    """クラスの追加・削除・名前変更・色変更を行うパネル。"""

    activeClassChanged = Signal(int)        # アクティブクラス（新規ボックス用）が変化
    classesEdited = Signal()                # 追加・名前変更・色変更（再描画用）
    classRemoved = Signal(int)              # 削除されたクラスのインデックス
    applyToSelectionRequested = Signal(int)  # 選択中ボックスへクラス適用を要求

    def __init__(self, classes: list[ClassDef], parent=None) -> None:
        super().__init__(parent)
        # メインウィンドウと共有するクラスリスト（同一オブジェクトを更新する）
        self.classes = classes
        self._build_ui()
        # 既定クラスがある場合は先頭を選択しておく
        self._refresh(0 if self.classes else None)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QLabel("クラス")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        hint = QLabel("数字キー1-9で選択 / ダブルクリックで選択中のボックスへ適用")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.list)

        grid = QGridLayout()
        self.btn_add = QPushButton("追加")
        self.btn_remove = QPushButton("削除")
        self.btn_rename = QPushButton("名前変更")
        self.btn_color = QPushButton("色変更")
        self.btn_add.clicked.connect(self._add)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_rename.clicked.connect(self._rename)
        self.btn_color.clicked.connect(self._recolor)
        grid.addWidget(self.btn_add, 0, 0)
        grid.addWidget(self.btn_remove, 0, 1)
        grid.addWidget(self.btn_rename, 1, 0)
        grid.addWidget(self.btn_color, 1, 1)
        layout.addLayout(grid)

        self.btn_apply = QPushButton("選択中のボックスに適用")
        self.btn_apply.clicked.connect(self._apply_to_selection)
        layout.addWidget(self.btn_apply)

    # ------------------------------------------------------------------
    # 表示更新
    # ------------------------------------------------------------------
    def _refresh(self, select_row: int | None) -> None:
        """リスト表示を作り直す（シグナルは抑制する）。"""
        self.list.blockSignals(True)
        self.list.clear()
        for index, cls in enumerate(self.classes):
            item = QListWidgetItem(_make_swatch(cls.color), f"{index}: {cls.name}")
            self.list.addItem(item)
        if select_row is not None and 0 <= select_row < len(self.classes):
            self.list.setCurrentRow(select_row)
        self.list.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_selection = self.list.currentRow() >= 0
        for btn in (self.btn_remove, self.btn_rename, self.btn_color, self.btn_apply):
            btn.setEnabled(has_selection)

    def active_class(self) -> int:
        """アクティブクラスのインデックス（未選択なら -1）。"""
        return self.list.currentRow()

    def select_class(self, index: int) -> None:
        """指定クラスをアクティブにする（数字キーから呼ばれる）。"""
        if 0 <= index < len(self.classes):
            self.list.setCurrentRow(index)

    def ensure_class(self, name: str) -> int:
        """名前でクラスを探し、無ければ追加してインデックスを返す。

        自動推論でモデルのクラスがアプリ未登録だった場合に使う。
        照合は大文字小文字を無視する。
        """
        lower = name.lower()
        for index, cls in enumerate(self.classes):
            if cls.name.lower() == lower:
                return index
        color = _PALETTE[len(self.classes) % len(_PALETTE)]
        self.classes.append(ClassDef(name, color))
        current = self.list.currentRow()
        self._refresh(current if current >= 0 else 0)
        self.classesEdited.emit()
        return len(self.classes) - 1

    # ------------------------------------------------------------------
    # シグナルハンドラ
    # ------------------------------------------------------------------
    def _on_row_changed(self, row: int) -> None:
        self._update_buttons()
        self.activeClassChanged.emit(row)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        if row >= 0:
            self.applyToSelectionRequested.emit(row)

    def _apply_to_selection(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.applyToSelectionRequested.emit(row)

    # ------------------------------------------------------------------
    # 編集操作
    # ------------------------------------------------------------------
    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "クラス追加", "クラス名:")
        if not ok or not name.strip():
            return
        color = _PALETTE[len(self.classes) % len(_PALETTE)]
        self.classes.append(ClassDef(name.strip(), color))
        new_index = len(self.classes) - 1
        self._refresh(new_index)
        self.classesEdited.emit()
        self.activeClassChanged.emit(new_index)

    def _rename(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        name, ok = QInputDialog.getText(
            self, "名前変更", "クラス名:", text=self.classes[row].name
        )
        if not ok or not name.strip():
            return
        self.classes[row].name = name.strip()
        self._refresh(row)
        self.classesEdited.emit()

    def _recolor(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        color = QColorDialog.getColor(
            QColor(self.classes[row].color), self, "クラスの色を選択"
        )
        if not color.isValid():
            return
        self.classes[row].color = color.name()
        self._refresh(row)
        self.classesEdited.emit()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        answer = QMessageBox.question(
            self,
            "クラス削除",
            f"クラス「{self.classes[row].name}」を削除しますか？\n"
            "このクラスのボックスは全画像から削除されます。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self.classes[row]
        new_row = min(row, len(self.classes) - 1) if self.classes else None
        self._refresh(new_row)
        self.classRemoved.emit(row)
        self.activeClassChanged.emit(self.list.currentRow())
