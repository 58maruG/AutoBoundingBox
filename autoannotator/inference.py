"""YOLO モデルによる自動推論。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal


@dataclass
class Detection:
    """1個の検出結果（画像ピクセル座標）。"""

    class_name: str
    x: float
    y: float
    w: float
    h: float
    confidence: float


class ModelRunner:
    """YOLO モデルを読み込み、画像から物体検出を行う。"""

    def __init__(self) -> None:
        self._model = None
        self._model_path = ""

    @property
    def model_path(self) -> str:
        return self._model_path

    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self, path: str) -> None:
        """モデルを読み込む。失敗時は RuntimeError を送出する。"""
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics がインストールされていません。"
            ) from exc
        try:
            self._model = YOLO(path)
        except Exception as exc:  # ultralytics は多様な例外を投げる
            raise RuntimeError(f"モデルを読み込めませんでした: {exc}") from exc
        self._model_path = path

    def predict(self, image_path: str, conf: float) -> list[Detection]:
        """1枚の画像を推論し、検出結果のリストを返す。"""
        if self._model is None:
            raise RuntimeError("モデルが読み込まれていません。")
        try:
            results = self._model.predict(
                source=image_path, conf=conf, verbose=False
            )
        except Exception as exc:
            raise RuntimeError(f"推論に失敗しました: {exc}") from exc

        detections: list[Detection] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            xyxy = boxes.xyxy.cpu().tolist()
            classes = boxes.cls.cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            for (x1, y1, x2, y2), cls_id, conf_value in zip(
                xyxy, classes, confidences
            ):
                cls_id = int(cls_id)
                name = names.get(cls_id, str(cls_id))
                detections.append(
                    Detection(
                        class_name=str(name),
                        x=float(x1),
                        y=float(y1),
                        w=float(x2 - x1),
                        h=float(y2 - y1),
                        confidence=float(conf_value),
                    )
                )
        return detections


class InferenceWorker(QThread):
    """複数画像の推論をバックグラウンドで実行するワーカー。"""

    progress = Signal(int, int)        # 完了枚数, 総枚数
    imageDone = Signal(int, list)      # 画像インデックス, list[Detection]
    failed = Signal(str)               # エラーメッセージ
    batchFinished = Signal(int, bool)  # 完了枚数, 中止されたか

    def __init__(
        self,
        runner: ModelRunner,
        jobs: list[tuple[int, str]],
        conf: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._jobs = jobs  # (画像インデックス, 画像パス) のリスト
        self._conf = conf
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        total = len(self._jobs)
        completed = 0
        for done, (index, path) in enumerate(self._jobs, start=1):
            if self._cancelled:
                break
            try:
                detections = self._runner.predict(path, self._conf)
            except RuntimeError as exc:
                self.failed.emit(str(exc))
                return
            self.imageDone.emit(index, detections)
            completed += 1
            self.progress.emit(done, total)
        self.batchFinished.emit(completed, self._cancelled)
