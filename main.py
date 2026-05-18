"""DCRsystem 自動アノテーションツール エントリポイント。"""

import os
import sys


def _run_selftest() -> int:
    """--selftest: 同梱された推論依存(torch / ultralytics)を検証する。

    結果を実行ファイルと同じ場所の selftest_result.json に書き出す。
    .exe が推論機能を正しく同梱できているか確認する診断用。
    """
    import json
    import traceback

    result: dict = {}
    try:
        import torch

        result["torch"] = torch.__version__
        result["cuda_available"] = bool(torch.cuda.is_available())
        if result["cuda_available"]:
            result["gpu"] = torch.cuda.get_device_name(0)
        from ultralytics import YOLO  # noqa: F401

        result["ultralytics_import"] = True
        result["ok"] = True
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"{exc}\n{traceback.format_exc()}"

    base = os.path.dirname(os.path.abspath(sys.executable))
    with open(
        os.path.join(base, "selftest_result.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_run_selftest())

    from autoannotator.main_window import main

    sys.exit(main())
