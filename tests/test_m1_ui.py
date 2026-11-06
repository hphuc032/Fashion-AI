from pathlib import Path

from streamlit.testing.v1 import AppTest
import streamlit as st
from tests.test_m1_integration import detect_fixture


def test_ocr_page_empty_state(tmp_path, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui-empty.db'}")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/main.py")).run(timeout=30)
    app.sidebar.radio[0].set_value("Nhận diện & Dịch").run()
    assert not app.exception
    assert app.title[-1].value == "Nhận diện & Dịch"
    assert any("Hãy tải một video" in item.value for item in app.info)


def test_ocr_page_existing_project_and_failed_job(m1, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setattr("app.ui.ocr_page.manager", lambda *args: None)
    settings, sessions, project = m1
    monkeypatch.setenv("STORAGE_ROOT", str(settings.storage_root))
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/main.py")).run(timeout=30)
    app.sidebar.radio[0].set_value("Nhận diện & Dịch").run()
    assert not app.exception
    assert any(s.label == "Chọn video để OCR" for s in app.selectbox)
    assert any(b.label == "Chạy OCR" for b in app.button)
    assert any("Chưa có đoạn chữ Trung" in info.value for info in app.info)


def test_populated_review_grid_and_frame_preview(m1, monkeypatch):
    st.cache_resource.clear()
    settings, sessions, project = m1
    detect_fixture(m1)
    monkeypatch.setenv("STORAGE_ROOT", str(settings.storage_root))
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setattr("app.ui.ocr_page.manager", lambda *args: None)
    # This test targets the actual Arrow-backed editor. Frame decoding is tested separately.
    monkeypatch.setattr("app.ui.ocr_page.diagnostic_preview", lambda *args: None)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/main.py")).run(timeout=30)
    app.sidebar.radio[0].set_value("Nhận diện & Dịch").run()
    assert not app.exception
    assert not app.error
    assert any(button.label == "Lưu chỉnh sửa" for button in app.button)
    assert any(button.label == "Dịch các đoạn đã chọn" for button in app.button)
