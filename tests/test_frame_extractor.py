from dataclasses import replace

import pytest
from PIL import Image

from app.services.frame_extractor import Cancelled, display_dimensions, extract_frames, sample_times
from app.utils.validators import UserError


@pytest.mark.parametrize("duration,interval,cap,expected", [(3, 1, 300, [0, 1, 2]), (1.1, .5, 300, [0, .5, 1]), (9, 1, 2, [0, 1]), (.02, 1, 300, [0])])
def test_source_timestamps_and_cap(duration, interval, cap, expected):
    assert sample_times(duration, interval, cap) == expected


@pytest.mark.parametrize("duration,interval,cap", [(0, 1, 3), (5, .01, 3), (float("nan"), 1, 3), (5, 1, 0)])
def test_invalid_sampling(duration, interval, cap):
    with pytest.raises(UserError):
        sample_times(duration, interval, cap)


def test_portrait_incremental_and_cache(m1, monkeypatch):
    settings, sessions, project = m1
    settings.ocr_max_frames = 2
    monkeypatch.setattr("app.services.frame_extractor.display_dimensions", lambda *args: (540, 960))
    calls = []

    def render(args, **kwargs):
        assert kwargs["shell"] is False and kwargs["timeout"] == 30
        calls.append(args)
        Image.new("RGB", (540, 960), "blue").save(args[-1])

    monkeypatch.setattr("app.services.frame_extractor.subprocess.run", render)
    path = settings.storage_root / project.file_path
    frames = extract_frames(path, project.id, 6, settings)
    first = next(frames)
    assert len(calls) == 1
    assert (first.original_width, first.original_height, first.width, first.height) == (540, 960, 540, 960)
    assert [f.timestamp for f in frames] == [1]
    cached = list(extract_frames(path, project.id, 6, settings))
    assert len(cached) == 2 and len(calls) == 2
    assert path.read_bytes() == b"unit-test-video"
    # Broken cached image gets regenerated rather than accepted.
    first.path.write_bytes(b"broken")
    next(extract_frames(path, project.id, 6, settings))
    assert len(calls) == 3


def test_cancel_before_decode(m1):
    settings, _, project = m1
    def cancel():
        raise Cancelled("cancel")
    with pytest.raises(Cancelled):
        next(extract_frames(settings.storage_root / project.file_path, project.id, 6, settings, cancel))


def test_bad_frame_and_outside_storage(m1, monkeypatch, tmp_path):
    settings, _, project = m1
    monkeypatch.setattr("app.services.frame_extractor.display_dimensions", lambda *args: (540, 960))
    monkeypatch.setattr("app.services.frame_extractor.subprocess.run", lambda *args, **kwargs: None)
    with pytest.raises(UserError, match="khung hình"):
        next(extract_frames(settings.storage_root / project.file_path, project.id, 6, settings))
    with pytest.raises(UserError):
        next(extract_frames(tmp_path / "outside.mp4", project.id, 6, settings))


def test_invalid_requested_timestamp(m1, monkeypatch):
    settings, _, project = m1
    monkeypatch.setattr("app.services.frame_extractor.display_dimensions", lambda *args: (540, 960))
    with pytest.raises(UserError):
        next(extract_frames(settings.storage_root / project.file_path, project.id, 6, settings, timestamps=[-1]))


@pytest.mark.parametrize("rotation,expected", [(0, (540, 960)), (90, (960, 540)), (180, (540, 960)), (270, (960, 540))])
def test_display_orientation(m1, monkeypatch, rotation, expected):
    import json
    from types import SimpleNamespace
    settings, _, project = m1
    result = {"streams": [{"width": 540, "height": 960, "side_data_list": [{"rotation": rotation}]}]}
    monkeypatch.setattr("app.services.frame_extractor.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(result)))
    assert display_dimensions(settings.storage_root / project.file_path, settings) == expected


def test_source_resolution_bound(m1, monkeypatch):
    settings, _, project = m1
    monkeypatch.setattr("app.services.frame_extractor.display_dimensions", lambda *args: (8000, 8000))
    with pytest.raises(UserError, match="Độ phân giải"):
        next(extract_frames(settings.storage_root / project.file_path, project.id, 6, settings))
