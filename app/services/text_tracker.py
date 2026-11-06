"""Conservative one-to-one text/spatial association at sampled timestamps."""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from uuid import uuid4


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]", text))


def box_iou(a: list, b: list) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    intersection = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0


@dataclass
class Detection:
    source_text: str
    confidence: float
    bounding_box: list[int]
    polygon: list[list[int]]
    timestamp: float
    frame_index: int
    frame_width: int
    frame_height: int
    id: str = field(default_factory=lambda: str(uuid4()))
    segment_id: str | None = None


@dataclass
class Segment:
    source_text: str
    start_time: float
    end_time: float
    bounding_box: list[int]
    confidence: float
    last_time: float
    id: str = field(default_factory=lambda: str(uuid4()))


def group_detections(detections: list[Detection], interval: float, duration: float,
                     min_confidence: float = 0.4, similarity: float = 0.94, iou: float = 0.3) -> list[Segment]:
    segments: list[Segment] = []
    used: set[tuple[str, int]] = set()
    for detection in sorted(detections, key=lambda d: (d.timestamp, -d.confidence, d.id)):
        if not contains_chinese(detection.source_text) or detection.confidence < min_confidence:
            continue
        text = normalized(detection.source_text)
        candidate = None
        best = -1.0
        for segment in segments:
            previous = normalized(segment.source_text)
            gap = detection.timestamp - segment.last_time
            # Numeric prices/size identifiers and Latin product codes must not drift.
            if re.findall(r"[A-Za-z0-9]+", text) != re.findall(r"[A-Za-z0-9]+", previous):
                continue
            score = SequenceMatcher(None, previous, text).ratio()
            # Short captions differing by even one character should stay distinct.
            same = text == previous or (min(len(text), len(previous)) >= 12 and score >= similarity)
            overlap = box_iou(segment.bounding_box, detection.bounding_box)
            if (same and 0 < gap <= interval * 1.1 and overlap >= iou
                    and (segment.id, detection.frame_index) not in used and score + overlap > best):
                candidate, best = segment, score + overlap
        end = min(duration, detection.timestamp + interval)
        if end <= detection.timestamp:
            continue
        if candidate is None:
            candidate = Segment(detection.source_text, detection.timestamp, end,
                                detection.bounding_box, detection.confidence, detection.timestamp)
            segments.append(candidate)
        else:
            candidate.end_time = end
            candidate.last_time = detection.timestamp
            if detection.confidence > candidate.confidence:
                candidate.source_text = detection.source_text
                candidate.bounding_box = detection.bounding_box
                candidate.confidence = detection.confidence
        detection.segment_id = candidate.id
        used.add((candidate.id, detection.frame_index))
    return segments
