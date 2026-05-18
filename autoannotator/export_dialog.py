"""書き出し設定ダイアログ。"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


@dataclass
class ExportConfig:
    """書き出し設定。"""

    mode: str  # "flat" / "train_val" / "train_val_test"
    ratios: dict[str, float] = field(default_factory=dict)
    seed: int = 42
    write_coco: bool = True


class ExportDialog(QDialog):
    """書き出し形式・分割比率を選ぶダイアログ。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("アノテーションの書き出し")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # --- 書き出し形式 ---
        mode_box = QGroupBox("書き出し形式")
        mode_layout = QVBoxLayout(mode_box)
        self.radio_flat = QRadioButton("フラット（labels/ のみ・分割なし）")
        self.radio_tv = QRadioButton("学習用データセット（train / val）")
        self.radio_tvt = QRadioButton(
            "学習用データセット（train / val / test）"
        )
        self.radio_tvt.setChecked(True)  # 既定は3分割
        for radio in (self.radio_flat, self.radio_tv, self.radio_tvt):
            mode_layout.addWidget(radio)
        layout.addWidget(mode_box)

        # --- 分割比率 ---
        self.ratio_box = QGroupBox("分割比率（％）")
        self._form = QFormLayout(self.ratio_box)
        self.spin_train = QSpinBox()
        self.spin_train.setRange(1, 98)
        self.spin_train.setValue(70)
        self.spin_val = QSpinBox()
        self.spin_val.setRange(1, 98)
        self.spin_val.setValue(20)
        self.lbl_remainder = QLabel()
        self._form.addRow("train ％", self.spin_train)   # row 0
        self._form.addRow("val ％", self.spin_val)        # row 1
        self._form.addRow("", self.lbl_remainder)         # row 2
        layout.addWidget(self.ratio_box)

        # --- オプション ---
        opt_box = QGroupBox("オプション")
        opt_form = QFormLayout(opt_box)
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 99999)
        self.spin_seed.setValue(42)
        opt_form.addRow("シャッフル seed", self.spin_seed)
        self.check_coco = QCheckBox("COCO JSON も出力する")
        self.check_coco.setChecked(True)
        opt_form.addRow(self.check_coco)
        layout.addWidget(opt_box)

        # --- ボタン ---
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for radio in (self.radio_flat, self.radio_tv, self.radio_tvt):
            radio.toggled.connect(self._update_state)
        self.spin_train.valueChanged.connect(self._update_state)
        self.spin_val.valueChanged.connect(self._update_state)
        self._update_state()

    # ------------------------------------------------------------------
    def _mode(self) -> str:
        if self.radio_flat.isChecked():
            return "flat"
        if self.radio_tv.isChecked():
            return "train_val"
        return "train_val_test"

    def _update_state(self) -> None:
        mode = self._mode()
        self.ratio_box.setEnabled(mode != "flat")
        if mode == "flat":
            return

        is_tvt = mode == "train_val_test"
        self._form.setRowVisible(1, is_tvt)  # val スピンボックスは3分割のみ

        if is_tvt:
            # test が1％以上になるよう val の上限を制限
            self.spin_val.setMaximum(max(1, 99 - self.spin_train.value()))
            test = 100 - self.spin_train.value() - self.spin_val.value()
            self.lbl_remainder.setText(f"test（残り）: {test} ％")
        else:
            val = 100 - self.spin_train.value()
            self.lbl_remainder.setText(f"val（残り）: {val} ％")

    def _on_accept(self) -> None:
        if self._mode() == "train_val_test":
            test = 100 - self.spin_train.value() - self.spin_val.value()
            if test < 1:
                QMessageBox.warning(
                    self,
                    "比率エラー",
                    "train + val が大きすぎます。"
                    "test が1％以上になるよう調整してください。",
                )
                return
        self.accept()

    def get_config(self) -> ExportConfig:
        """ダイアログの設定を ExportConfig として返す。"""
        mode = self._mode()
        if mode == "flat":
            ratios: dict[str, float] = {}
        elif mode == "train_val":
            train = self.spin_train.value() / 100
            ratios = {"train": train, "val": round(1 - train, 4)}
        else:
            train = self.spin_train.value() / 100
            val = self.spin_val.value() / 100
            ratios = {
                "train": train,
                "val": val,
                "test": round(1 - train - val, 4),
            }
        return ExportConfig(
            mode=mode,
            ratios=ratios,
            seed=self.spin_seed.value(),
            write_coco=self.check_coco.isChecked(),
        )
