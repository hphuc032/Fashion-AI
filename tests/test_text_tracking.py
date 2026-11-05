import pytest

from app.services.text_tracker import Detection, box_iou, contains_chinese, group_detections


def detection(text="男生穿搭", time=0, box=None, confidence=.95):
    return Detection(text, confidence, box or [10, 10, 100, 30], [[10, 10], [110, 10], [110, 40], [10, 40]], time, int(time), 540, 960)


def test_consecutive_duplicates_and_best_confidence():
    raw = [detection(time=i, confidence=.8 + i * .05) for i in range(3)]
    segments = group_detections(raw, 1, 3)
    assert len(segments) == 1 and segments[0].end_time == 3
    assert segments[0].confidence == pytest.approx(.9)
    assert all(d.segment_id == segments[0].id for d in raw)


@pytest.mark.parametrize("second", ["女生穿搭", "男生穿衣", "男生穿搭123"])
def test_different_short_captions_do_not_merge(second):
    assert len(group_detections([detection(), detection(second, time=1)], 1, 3)) == 2


def test_similar_price_or_identifier_change():
    a = "秋冬新款这件衬衫今天优惠价格99元"
    b = "秋冬新款这件衬衫今天优惠价格98元"
    assert len(group_detections([detection(a), detection(b, time=1)], 1, 3)) == 2


def test_spatially_distinct_boxes_and_same_frame():
    raw = [detection(), detection(box=[300, 400, 100, 30]), detection(time=1), detection(time=1, box=[300, 400, 100, 30])]
    assert len(group_detections(raw, 1, 3)) == 2


def test_text_disappears_and_reappears():
    assert len(group_detections([detection(), detection(time=3)], 1, 5)) == 2


def test_low_confidence_english_numeric_and_mixed_language():
    raw = [detection(confidence=.2), detection("ABC"), detection("123"), detection("衬衫 ABC 123", time=1)]
    segments = group_detections(raw, 1, 4)
    assert len(segments) == 1 and segments[0].source_text == "衬衫 ABC 123"
    assert all(d.segment_id is None for d in raw[:3])


def test_cjk_and_iou():
    assert contains_chinese("繁體中文") and contains_chinese("中文English")
    assert not contains_chinese("123 ABC")
    assert box_iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(1 / 3)
    assert box_iou([0, 0, 10, 10], [30, 30, 10, 10]) == 0
