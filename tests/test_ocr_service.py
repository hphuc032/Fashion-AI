from pathlib import Path

import pytest

from app.providers.ocr.paddle_provider import PaddleProvider, normalize_result
from app.services.frame_extractor import SampledFrame
from app.utils.validators import UserError


def test_normalize_multiple_mixed_and_scale():
    frame = SampledFrame(2, 2, Path("sample.png"), 1080, 1920, 540, 960)
    result = {"rec_texts": ["男生穿搭", "ABC 123"], "rec_scores": [.98, .3],
              "rec_polys": [[[10, 20], [110, 20], [110, 50], [10, 50]], [[20, 200], [100, 200], [100, 220], [20, 220]]]}
    detections = normalize_result(result, frame)
    assert len(detections) == 2
    assert detections[0].bounding_box == [20, 40, 200, 60]
    assert detections[0].timestamp == 2 and detections[0].frame_index == 2
    assert detections[1].confidence == .3  # Raw low-confidence results retained.


@pytest.mark.parametrize("result", [{}, {"rec_texts": ["中"], "rec_scores": [], "rec_polys": []},
                                      {"rec_texts": ["中"], "rec_scores": [float("nan")], "rec_polys": [[[1, 1]] * 4]}])
def test_invalid_vendor_result(result):
    with pytest.raises(UserError):
        normalize_result(result, SampledFrame(0, 0, Path("x"), 10, 10, 10, 10))


def test_missing_models(m1):
    settings, _, _ = m1
    with pytest.raises(UserError, match="Thiếu mô hình OCR"):
        PaddleProvider(settings)._load()
