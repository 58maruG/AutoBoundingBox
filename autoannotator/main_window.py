"""メインウィンドウ。"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImageReader, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from autoannotator.canvas import AnnotationCanvas
from autoannotator.class_panel import ClassPanel
from autoannotator.export_dialog import ExportDialog
from autoannotator.exporter import export_coco, export_training_dataset, export_yolo
from autoannotator.inference import InferenceWorker, ModelRunner
from autoannotator.inference_panel import InferencePanel
from autoannotator.models import (
    IMAGE_EXTENSIONS,
    BBox,
    ClassDef,
    ImageItem,
    default_classes,
)
from autoannotator.result_panel import ResultPanel

APP_NAME = "DCRsystem 自動アノテーションツール"


class MainWindow(QMainWindow):
    """アプリケーションのメインウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 840)

        self.images: list[ImageItem] = []
        self.current_index: int = -1
        self.current_folder: str = ""
        # 既定の6クラスで初期化（ClassPanel と共有する）
        self.classes: list[ClassDef] = default_classes()

        # 画像一覧フィルター状態: "all" / "class" / "multi"
        self._filter_mode: str = "all"
        self._filter_class: int = -1

        # 推論まわり
        self.model_runner = ModelRunner()
        self._worker: InferenceWorker | None = None
        self._progress: QProgressDialog | None = None

        self._build_ui()
        self._build_actions()
        self._connect_signals()

        self.canvas.set_classes(self.classes)
        self.canvas.set_active_class(self.class_panel.active_class())
        self._refresh_results()
        self._update_nav_state()
        self._update_edit_state()
        self._update_inference_state()
        self.statusBar().showMessage("画像フォルダを開いてください")

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # 左: 画像一覧
        self.image_list = QListWidget()
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_layout.addWidget(QLabel("画像一覧"))
        list_layout.addWidget(self.image_list)

        # 中央: キャンバス
        self.canvas = AnnotationCanvas()

        # 右サイドバーの左: 結果パネル（クラス別集計・フィルター）
        self.result_panel = ResultPanel()

        # 右: 推論パネル + クラスパネル
        self.inference_panel = InferencePanel()
        self.class_panel = ClassPanel(self.classes)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.inference_panel)
        right_layout.addWidget(self.class_panel, 1)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(list_panel)
        self.splitter.addWidget(self.canvas)
        self.splitter.addWidget(self.result_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setStretchFactor(3, 0)
        self.splitter.setSizes([200, 670, 250, 270])

        self.setCentralWidget(self.splitter)

    def _build_actions(self) -> None:
        menubar = self.menuBar()
        toolbar = self.addToolBar("メイン")
        toolbar.setMovable(False)

        # ファイル
        self.act_open = QAction("画像フォルダを開く", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.open_folder)

        self.act_export = QAction("アノテーションを書き出す", self)
        self.act_export.setShortcut(QKeySequence.StandardKey.Save)
        self.act_export.triggered.connect(self._export_annotations)

        self.act_quit = QAction("終了", self)
        self.act_quit.triggered.connect(self.close)

        # 移動（A=前 / D=次）
        self.act_prev = QAction("前の画像", self)
        self.act_prev.setShortcut(QKeySequence("A"))
        self.act_prev.triggered.connect(self.prev_image)

        self.act_next = QAction("次の画像", self)
        self.act_next.setShortcut(QKeySequence("D"))
        self.act_next.triggered.connect(self.next_image)

        # 編集
        self.act_undo = QAction("元に戻す", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.canvas.undo)

        self.act_copy = QAction("コピー", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.triggered.connect(self.canvas.copy_selected)

        self.act_paste = QAction("貼り付け", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.triggered.connect(self.canvas.paste_boxes)

        self.act_delete = QAction("選択ボックスを削除", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self.canvas.delete_selected)

        # 推論
        self.act_load_model = QAction("モデル選択 (.pt)", self)
        self.act_load_model.triggered.connect(self._load_model)

        self.act_predict_current = QAction("現在の画像を推論", self)
        self.act_predict_current.triggered.connect(self._predict_current)

        self.act_predict_all = QAction("全画像を推論", self)
        self.act_predict_all.triggered.connect(self._predict_all)

        # 表示
        self.act_fit = QAction("全体表示", self)
        self.act_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.act_fit.triggered.connect(self.canvas.fit_to_window)

        self.act_zoom_in = QAction("ズームイン", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.triggered.connect(self.canvas.zoom_in)

        self.act_zoom_out = QAction("ズームアウト", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.triggered.connect(self.canvas.zoom_out)

        # メニュー
        file_menu = menubar.addMenu("ファイル")
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_export)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        nav_menu = menubar.addMenu("移動")
        nav_menu.addAction(self.act_prev)
        nav_menu.addAction(self.act_next)

        edit_menu = menubar.addMenu("編集")
        edit_menu.addAction(self.act_undo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_copy)
        edit_menu.addAction(self.act_paste)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_delete)

        infer_menu = menubar.addMenu("推論")
        infer_menu.addAction(self.act_load_model)
        infer_menu.addSeparator()
        infer_menu.addAction(self.act_predict_current)
        infer_menu.addAction(self.act_predict_all)

        view_menu = menubar.addMenu("表示")
        view_menu.addAction(self.act_fit)
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)

        # ツールバー
        for action in (
            self.act_open, self.act_export, None,
            self.act_prev, self.act_next, None,
            self.act_load_model, self.act_predict_current,
            self.act_predict_all, None,
            self.act_undo, self.act_copy, self.act_paste,
            self.act_delete, None,
            self.act_fit, self.act_zoom_in, self.act_zoom_out,
        ):
            if action is None:
                toolbar.addSeparator()
            else:
                toolbar.addAction(action)

        # 数字キー 1-9 でクラス選択
        for number in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(number)), self)
            shortcut.activated.connect(
                lambda index=number - 1: self._quick_select_class(index)
            )

        # Esc で操作キャンセル・選択解除
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.canvas.cancel_action)

    def _connect_signals(self) -> None:
        self.image_list.currentRowChanged.connect(self._on_list_row_changed)

        self.class_panel.activeClassChanged.connect(self.canvas.set_active_class)
        self.class_panel.classesEdited.connect(self.canvas.repaint_boxes)
        self.class_panel.classesEdited.connect(self._refresh_results)
        self.class_panel.classRemoved.connect(self._on_class_removed)
        self.class_panel.applyToSelectionRequested.connect(
            self._apply_class_to_selection
        )

        self.inference_panel.modelLoadRequested.connect(self._load_model)
        self.inference_panel.predictCurrentRequested.connect(
            self._predict_current
        )
        self.inference_panel.predictAllRequested.connect(self._predict_all)

        self.canvas.boxesChanged.connect(self._on_boxes_changed)
        self.canvas.selectionChanged.connect(self._update_edit_state)
        self.canvas.drawBlocked.connect(self._on_draw_blocked)

        self.result_panel.classFilterRequested.connect(self._on_filter_by_class)
        self.result_panel.allFilterRequested.connect(self._on_filter_all)
        self.result_panel.multiBboxFilterRequested.connect(
            self._on_filter_multi
        )

    # ------------------------------------------------------------------
    # フォルダ読み込み
    # ------------------------------------------------------------------
    def open_folder(self) -> None:
        """画像フォルダを選択して取り込む。"""
        folder = QFileDialog.getExistingDirectory(self, "画像フォルダを選択")
        if not folder:
            return

        try:
            names = sorted(
                f
                for f in os.listdir(folder)
                if f.lower().endswith(IMAGE_EXTENSIONS)
            )
        except OSError as exc:
            QMessageBox.critical(
                self, "エラー", f"フォルダを読み込めませんでした:\n{exc}"
            )
            return

        if not names:
            QMessageBox.information(
                self, "画像なし", "対応する画像ファイルが見つかりませんでした。"
            )
            return

        self.images = [
            ImageItem(path=os.path.join(folder, name)) for name in names
        ]
        self.current_index = -1
        self.current_folder = folder

        self.image_list.blockSignals(True)
        self.image_list.clear()
        for item in self.images:
            self.image_list.addItem(QListWidgetItem(os.path.basename(item.path)))
        self.image_list.blockSignals(False)

        # フォルダを開き直したらフィルターは全表示に戻す
        self._filter_mode = "all"
        self._filter_class = -1
        self.result_panel.clear_class_selection()

        self.set_current(0)
        self._update_inference_state()
        self._refresh_results()
        self.statusBar().showMessage(
            f"{len(self.images)} 枚の画像を読み込みました", 5000
        )

    # ------------------------------------------------------------------
    # ナビゲーション
    # ------------------------------------------------------------------
    def _visible_indices(self) -> list[int]:
        """現在フィルターで表示中の画像インデックス一覧を返す。"""
        return [
            i
            for i in range(self.image_list.count())
            if not self.image_list.item(i).isHidden()
        ]

    def set_current(self, index: int) -> None:
        """指定インデックスの画像を表示する。"""
        if not self.images or not (0 <= index < len(self.images)):
            return

        self.current_index = index
        item = self.images[index]

        if self.canvas.show_image_item(item):
            item.width, item.height = self.canvas.image_size()
        else:
            self.canvas.clear_image()
            QMessageBox.warning(
                self, "読み込み失敗", f"画像を表示できませんでした:\n{item.path}"
            )

        self.image_list.blockSignals(True)
        self.image_list.setCurrentRow(index)
        self.image_list.blockSignals(False)

        self._update_nav_state()
        self._update_edit_state()
        self._update_status()

    def _on_list_row_changed(self, row: int) -> None:
        if row >= 0:
            self.set_current(row)

    def prev_image(self) -> None:
        """フィルター内で前の画像へ移動する。"""
        visible = self._visible_indices()
        candidates = [i for i in visible if i < self.current_index]
        if candidates:
            self.set_current(candidates[-1])

    def next_image(self) -> None:
        """フィルター内で次の画像へ移動する。"""
        visible = self._visible_indices()
        candidates = [i for i in visible if i > self.current_index]
        if candidates:
            self.set_current(candidates[0])

    # ------------------------------------------------------------------
    # クラス別集計・フィルター
    # ------------------------------------------------------------------
    def _refresh_results(self) -> None:
        """結果パネルの集計を更新し、フィルターを再適用する。"""
        self.result_panel.refresh(self.classes, self.images)
        self._apply_filter()

    def _apply_filter(self) -> None:
        """現在のフィルター設定に従い画像一覧の表示・非表示を更新する。"""
        visible_count = 0
        for i, image in enumerate(self.images):
            list_item = self.image_list.item(i)
            if list_item is None:
                continue
            if self._filter_mode == "class":
                show = any(
                    b.class_id == self._filter_class for b in image.boxes
                )
            elif self._filter_mode == "multi":
                show = len(image.boxes) >= 2
            else:
                show = True
            list_item.setHidden(not show)
            if show:
                visible_count += 1

        total = len(self.images)
        if (
            self._filter_mode == "class"
            and 0 <= self._filter_class < len(self.classes)
        ):
            name = self.classes[self._filter_class].name
            status = f"表示中: {name}（{visible_count}/{total} 枚）"
        elif self._filter_mode == "multi":
            status = f"表示中: 複数bbox画像（{visible_count}/{total} 枚）"
        else:
            status = f"表示中: すべて（{total} 枚）"
        self.result_panel.set_status(status)

        self._update_nav_state()

    def _on_filter_by_class(self, class_id: int) -> None:
        """結果パネルのクラスがクリックされたとき: そのクラスで絞り込む。"""
        if not (0 <= class_id < len(self.classes)):
            return
        self._filter_mode = "class"
        self._filter_class = class_id
        self._apply_filter()
        self._jump_into_filter()

    def _on_filter_all(self) -> None:
        """「全てのクラスを表示」: フィルターを解除する。"""
        self._filter_mode = "all"
        self._filter_class = -1
        self.result_panel.clear_class_selection()
        self._apply_filter()

    def _on_filter_multi(self) -> None:
        """「複数bbox画像のみ表示」: bbox 2個以上の画像で絞り込む。"""
        self._filter_mode = "multi"
        self._filter_class = -1
        self.result_panel.clear_class_selection()
        self._apply_filter()
        self._jump_into_filter()

    def _jump_into_filter(self) -> None:
        """フィルター適用後、現在画像が範囲外なら先頭の表示画像へ移動する。"""
        visible = self._visible_indices()
        if visible and self.current_index not in visible:
            self.set_current(visible[0])

    # ------------------------------------------------------------------
    # クラス操作
    # ------------------------------------------------------------------
    def _quick_select_class(self, index: int) -> None:
        """数字キー: クラスを選択し、選択中ボックスにも適用する。"""
        if not (0 <= index < len(self.classes)):
            return
        self.class_panel.select_class(index)
        self.canvas.apply_class_to_selection(index)
        self._update_status()

    def _apply_class_to_selection(self, index: int) -> None:
        self.canvas.apply_class_to_selection(index)
        self._update_status()

    def _on_class_removed(self, removed_index: int) -> None:
        """クラス削除時、全画像のボックスのクラスIDを振り直す。"""
        for image in self.images:
            kept: list[BBox] = []
            for box in image.boxes:
                if box.class_id == removed_index:
                    continue  # 削除されたクラスのボックスは破棄
                if box.class_id > removed_index:
                    box.class_id -= 1
                kept.append(box)
            image.boxes = kept
        self.canvas.reload_boxes()
        # クラスIDがずれるため、クラス絞り込み中なら全表示に戻す
        if self._filter_mode == "class":
            self._filter_mode = "all"
            self._filter_class = -1
            self.result_panel.clear_class_selection()
        self._refresh_results()
        self._update_status()
        self._update_edit_state()

    # ------------------------------------------------------------------
    # 自動推論
    # ------------------------------------------------------------------
    def _load_model(self) -> None:
        """YOLO モデル(.pt)を選択して読み込む。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "YOLOモデルを選択", self.current_folder, "YOLOモデル (*.pt)"
        )
        if not path:
            return

        self.statusBar().showMessage("モデルを読み込み中...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            self.model_runner.load(path)
        except RuntimeError as exc:
            QMessageBox.critical(self, "モデル読み込みエラー", str(exc))
            self.statusBar().clearMessage()
            return
        finally:
            QApplication.restoreOverrideCursor()

        name = os.path.basename(path)
        self.inference_panel.set_model_name(name)
        self.statusBar().showMessage(f"モデルを読み込みました: {name}", 5000)
        self._update_inference_state()

    def _check_model(self) -> bool:
        if not self.model_runner.is_loaded():
            QMessageBox.information(
                self,
                "モデル未読み込み",
                "先に「モデル選択 (.pt)」でYOLOモデルを読み込んでください。",
            )
            return False
        return True

    def _predict_current(self) -> None:
        """現在表示中の画像を推論する。"""
        if not self._check_model() or self.current_index < 0:
            return
        item = self.images[self.current_index]
        if item.boxes:
            answer = QMessageBox.question(
                self,
                "確認",
                f"この画像の既存ボックス {len(item.boxes)} 個を"
                "推論結果で置き換えますか？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        conf = self.inference_panel.confidence()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            detections = self.model_runner.predict(item.path, conf)
        except RuntimeError as exc:
            QMessageBox.critical(self, "推論エラー", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        item.boxes = self._detections_to_boxes(detections)
        self.canvas.reload_boxes()
        self._refresh_results()
        self._update_status()
        self._update_edit_state()
        self.statusBar().showMessage(
            f"{len(detections)} 個のボックスを生成しました", 5000
        )

    def _predict_all(self) -> None:
        """ボックスが無い全画像をまとめて推論する。"""
        if not self._check_model() or not self.images:
            return

        targets = [
            (i, img.path)
            for i, img in enumerate(self.images)
            if not img.boxes
        ]
        skipped = len(self.images) - len(targets)
        if not targets:
            QMessageBox.information(
                self, "推論", "未アノテーションの画像がありません。"
            )
            return

        message = f"{len(targets)} 枚を推論します。"
        if skipped:
            message += f"\n（既にボックスがある {skipped} 枚はスキップします）"
        if (
            QMessageBox.question(self, "全画像を推論", message)
            != QMessageBox.StandardButton.Yes
        ):
            return

        self._start_batch_inference(targets, self.inference_panel.confidence())

    def _start_batch_inference(
        self, targets: list[tuple[int, str]], conf: float
    ) -> None:
        self._progress = QProgressDialog(
            "推論中...", "キャンセル", 0, len(targets), self
        )
        self._progress.setWindowTitle("全画像を推論")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        self._worker = InferenceWorker(self.model_runner, targets, conf)
        self._worker.progress.connect(self._on_inference_progress)
        self._worker.imageDone.connect(self._on_inference_image_done)
        self._worker.failed.connect(self._on_inference_failed)
        self._worker.batchFinished.connect(self._on_inference_done)
        self._progress.canceled.connect(self._worker.cancel)

        self.inference_panel.set_busy(True)
        self._worker.start()

    def _on_inference_progress(self, done: int, total: int) -> None:
        if self._progress is not None:
            self._progress.setLabelText(f"推論中... {done} / {total}")
            self._progress.setValue(done)

    def _on_inference_image_done(self, index: int, detections: list) -> None:
        if 0 <= index < len(self.images):
            self.images[index].boxes = self._detections_to_boxes(detections)
            if index == self.current_index:
                self.canvas.reload_boxes()
                self._update_status()

    def _on_inference_failed(self, message: str) -> None:
        self._finish_batch()
        QMessageBox.critical(self, "推論エラー", message)

    def _on_inference_done(self, completed: int, cancelled: bool) -> None:
        self._finish_batch()

        # クラス別ボックス数を集計して表示
        counts = self._count_classes()
        if counts:
            count_lines = "\n".join(
                f"  {self.classes[cid].name}: {n}個"
                for cid, n in sorted(counts.items())
                if 0 <= cid < len(self.classes)
            )
            count_section = f"\n\n【クラス別ボックス数（全画像合計）】\n{count_lines}"
        else:
            count_section = ""

        if cancelled:
            title = "推論中止"
            body = f"中止しました（{completed} 枚処理済み）。"
        else:
            title = "推論完了"
            body = f"{completed} 枚の推論が完了しました。"

        QMessageBox.information(self, title, body + count_section)

    def _finish_batch(self) -> None:
        """バッチ推論の後始末をする。"""
        if self._worker is not None:
            self._worker.wait()
            self._worker = None
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self.inference_panel.set_busy(False)
        self.canvas.reload_boxes()
        self._refresh_results()
        self._update_status()
        self._update_edit_state()
        self._update_inference_state()

    def _detections_to_boxes(self, detections: list) -> list[BBox]:
        """推論結果を BBox のリストに変換する。

        モデルのクラス名がアプリ未登録なら自動でクラスを追加する。
        """
        boxes: list[BBox] = []
        for det in detections:
            class_id = self.class_panel.ensure_class(det.class_name)
            boxes.append(
                BBox(
                    class_id=class_id,
                    x=det.x,
                    y=det.y,
                    w=det.w,
                    h=det.h,
                    confidence=det.confidence,
                )
            )
        return boxes

    # ------------------------------------------------------------------
    # クラス別カウント
    # ------------------------------------------------------------------
    def _count_classes(self) -> dict[int, int]:
        """全画像のクラスごとのボックス数を返す。"""
        counts: dict[int, int] = {}
        for image in self.images:
            for box in image.boxes:
                counts[box.class_id] = counts.get(box.class_id, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # 書き出し
    # ------------------------------------------------------------------
    def _ensure_image_sizes(self) -> None:
        """未表示でサイズ未取得の画像の幅・高さを補完する。"""
        for image in self.images:
            if image.width > 0 and image.height > 0:
                continue
            size = QImageReader(image.path).size()
            if size.isValid():
                image.width = size.width()
                image.height = size.height()

    def _export_annotations(self) -> None:
        """アノテーションを書き出す（形式・分割はダイアログで選択）。"""
        if not self.images:
            QMessageBox.information(
                self, "書き出し", "画像が読み込まれていません。"
            )
            return

        dialog = ExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        config = dialog.get_config()

        output_dir = QFileDialog.getExistingDirectory(
            self, "書き出し先フォルダを選択", self.current_folder
        )
        if not output_dir:
            return

        self._ensure_image_sizes()
        missing = sum(
            1 for img in self.images if img.width <= 0 or img.height <= 0
        )

        counts: dict[str, int] = {}
        try:
            if config.mode == "flat":
                export_yolo(self.images, self.classes, output_dir)
                if config.write_coco:
                    export_coco(
                        self.images,
                        self.classes,
                        os.path.join(output_dir, "annotations_coco.json"),
                    )
                detail = "labels\\*.txt（フラット）, classes.txt, data.yaml"
            else:
                counts = export_training_dataset(
                    self.images,
                    self.classes,
                    output_dir,
                    config.ratios,
                    config.seed,
                    config.write_coco,
                )
                detail = (
                    "images\\<split>\\ ＋ labels\\<split>\\ ＋ "
                    "data.yaml（学習にそのまま使用可）"
                )
        except OSError as exc:
            QMessageBox.critical(
                self, "書き出し失敗", f"書き出しに失敗しました:\n{exc}"
            )
            return

        total_boxes = sum(len(img.boxes) for img in self.images)
        message = (
            f"{len(self.images)} 枚 / 合計 {total_boxes} 個のボックスを"
            f"書き出しました。\n\n出力先: {output_dir}\n  {detail}"
        )
        if counts:
            split_text = " / ".join(
                f"{name} {n}枚" for name, n in counts.items()
            )
            message += f"\n\n分割: {split_text}"
            empty = [name for name, n in counts.items() if n == 0]
            if empty:
                message += (
                    f"\n※ 画像数が少なく空の split があります: "
                    f"{', '.join(empty)}"
                )
        if missing:
            message += (
                f"\n\n※ サイズを取得できなかった画像が {missing} 枚あり、"
                "その .txt は空になりました。"
            )
        QMessageBox.information(self, "書き出し完了", message)
        self.statusBar().showMessage(
            f"{total_boxes} 個のボックスを書き出しました", 5000
        )

    # ------------------------------------------------------------------
    # 状態更新
    # ------------------------------------------------------------------
    def _on_boxes_changed(self) -> None:
        self._refresh_results()
        self._update_status()
        self._update_edit_state()

    def _on_draw_blocked(self) -> None:
        QMessageBox.information(
            self,
            "クラス未選択",
            "ボックスを描く前に、右側のパネルでクラスを追加・選択してください。",
        )

    def _update_nav_state(self) -> None:
        has_images = bool(self.images)
        visible = self._visible_indices() if has_images else []
        self.act_prev.setEnabled(
            has_images and any(i < self.current_index for i in visible)
        )
        self.act_next.setEnabled(
            has_images and any(i > self.current_index for i in visible)
        )
        for action in (self.act_fit, self.act_zoom_in, self.act_zoom_out):
            action.setEnabled(has_images)
        self.act_export.setEnabled(has_images)

    def _update_edit_state(self) -> None:
        has_sel = self.canvas.has_selection()
        has_image = self.current_index >= 0
        self.act_delete.setEnabled(has_sel)
        self.act_copy.setEnabled(has_sel)
        self.act_undo.setEnabled(self.canvas.can_undo())
        self.act_paste.setEnabled(self.canvas.has_clipboard() and has_image)

    def _update_inference_state(self) -> None:
        ready = self.model_runner.is_loaded() and bool(self.images)
        self.inference_panel.set_predict_enabled(ready)
        self.act_predict_current.setEnabled(ready)
        self.act_predict_all.setEnabled(ready)

    def _update_status(self) -> None:
        if self.current_index < 0:
            self.statusBar().showMessage("画像フォルダを開いてください")
            return
        item = self.images[self.current_index]
        name = os.path.basename(item.path)
        resolution = f"{item.width}×{item.height}" if item.width else "サイズ不明"
        self.statusBar().showMessage(
            f"{self.current_index + 1} / {len(self.images)}    "
            f"{name}    {resolution}    ボックス {len(item.boxes)} 個"
        )


def main() -> int:
    """アプリケーションを起動する。"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
