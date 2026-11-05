from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui.db'}")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/main.py")).run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "Fashion AI Localizer"
    assert len(app.metric) == 3
    app.sidebar.radio[0].set_value("Tải video").run()
    assert not app.exception
    assert app.button[0].label == "Lưu video"
    app.button[0].click().run()
    assert app.warning[0].value == "Hãy chọn một video trước khi lưu."
    app.sidebar.radio[0].set_value("Thư viện").run()
    assert not app.exception
