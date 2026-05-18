"""自動推論の操作パネル。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class InferencePanel(QWidget):
    """モデル読み込みと推論実行を行うパネル。"""

    modelLoadRequested = Signal()
    predictCurrentRequested = Signal()
    predictAllRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QLabel("自動推論")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.btn_model = QPushButton("モデル選択 (.pt)")
        self.btn_model.clicked.connect(lambda: self.modelLoadRequested.emit())
        layout.addWidget(self.btn_model)

        self.model_label = QLabel("モデル: 未読み込み")
        self.model_label.setWordWrap(True)
        self.model_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.model_label)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("信頼度しきい値"))
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.05, 0.95)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        conf_row.addWidget(self.conf_spin)
        conf_row.addStretch()
        layout.addLayout(conf_row)

        self.btn_predict_current = QPushButton("現在の画像を推論")
        self.btn_predict_all = QPushButton("全画像を推論")
        self.btn_predict_current.clicked.connect(
            lambda: self.predictCurrentRequested.emit()
        )
        self.btn_predict_all.clicked.connect(
            lambda: self.predictAllRequested.emit()
        )
        layout.addWidget(self.btn_predict_current)
        layout.addWidget(self.btn_predict_all)

        self.set_predict_enabled(False)

    # ------------------------------------------------------------------
    def confidence(self) -> float:
        """信頼度しきい値を返す。"""
        return self.conf_spin.value()

    def set_model_name(self, name: str) -> None:
        """読み込み済みモデル名を表示する。"""
        self.model_label.setText(f"モデル: {name}")

    def set_predict_enabled(self, enabled: bool) -> None:
        """推論ボタンの有効/無効を切り替える。"""
        self.btn_predict_current.setEnabled(enabled)
        self.btn_predict_all.setEnabled(enabled)

    def set_busy(self, busy: bool) -> None:
        """推論実行中はパネル全体を無効化する。"""
        self.btn_model.setEnabled(not busy)
        self.conf_spin.setEnabled(not busy)
        self.btn_predict_current.setEnabled(not busy)
        self.btn_predict_all.setEnabled(not busy)
