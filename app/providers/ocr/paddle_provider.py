"""PaddleOCR 3 adapter; all vendor output normalization lives here."""
import math
import os
from pathlib import Path

from app.core.config import Settings
from app.services.frame_extractor import SampledFrame
from app.services.text_tracker import Detection
from app.utils.validators import UserError

MODEL_NAMES = ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec")
MODEL_VERSION = "paddleocr-3.3.2-ppocrv5-mobile"


def normalize_result(result: dict, frame: SampledFrame) -> list[Detection]:
    try:
        texts, scores = result["rec_texts"], result["rec_scores"]
        polygons = result["rec_polys"]
        if not len(texts) == len(scores) == len(polygons):
            raise ValueError()
        detections = []
        for text, score, polygon in zip(texts, scores, polygons):
            score = float(score)
            if not math.isfinite(score) or not 0 <= score <= 1 or len(polygon) != 4:
                raise ValueError()
            if not isinstance(text, str) or not text.strip():
                continue
            points = []
            for px, py in polygon:
                if not math.isfinite(float(px)) or not math.isfinite(float(py)):
                    raise ValueError()
                points.append([max(0, min(frame.original_width, round(float(px) * frame.original_width / frame.width))),
                               max(0, min(frame.original_height, round(float(py) * frame.original_height / frame.height)))])
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
            if box[2] <= 0 or box[3] <= 0:
                continue
            detections.append(Detection(text.strip(), score, box, points, frame.timestamp,
                                        frame.index, frame.original_width, frame.original_height))
        return detections
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise UserError("Kết quả PaddleOCR không đúng định dạng hỗ trợ. Kiểm tra phiên bản thư viện.") from exc


class PaddleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = None

    def _load(self):
        if self.engine is not None:
            return self.engine
        folder = self.settings.ocr_models_dir or self.settings.storage_root / "models" / "paddle"
        paths = [folder / name for name in MODEL_NAMES]
        if not all((p / "inference.yml").is_file() for p in paths):
            raise UserError("Thiếu mô hình OCR. Chạy scripts/setup_m1_models.py --ocr sau khi cài requirements-m1.txt.")
        try:
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(self.settings.storage_root / "models" / "paddlex-cache"))
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from paddleocr import PaddleOCR
            self.engine = PaddleOCR(
                text_detection_model_name=MODEL_NAMES[0], text_detection_model_dir=str(paths[0]),
                text_recognition_model_name=MODEL_NAMES[1], text_recognition_model_dir=str(paths[1]),
                use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                device="gpu:0" if self.settings.ocr_enable_gpu else "cpu",
                cpu_threads=self.settings.ocr_cpu_threads, enable_mkldnn=False,
                text_rec_score_thresh=0.0,
            )
        except ImportError as exc:
            raise UserError("Chưa cài PaddleOCR/PaddlePaddle. Cài requirements-m1.txt bằng Python 3.11.") from exc
        except Exception as exc:
            raise UserError("Không khởi tạo được PaddleOCR. Kiểm tra mô hình, PaddlePaddle CPU/GPU và nhật ký worker.") from exc
        return self.engine

    def detect(self, frame: SampledFrame) -> list[Detection]:
        try:
            results = self._load().predict(str(frame.path))
            detections = []
            for result in results:
                detections.extend(normalize_result(result, frame))
            return detections
        except UserError:
            raise
        except Exception as exc:
            raise UserError("PaddleOCR không nhận diện được khung hình. Hãy kiểm tra mô hình hoặc thử lại.") from exc
