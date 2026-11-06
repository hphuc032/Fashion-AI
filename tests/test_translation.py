import time

import pytest
from sqlalchemy import select

from app.database.m1_models import TranslationCache
from app.providers.translation.argos_provider import ArgosProvider, FASHION_TERMS
from app.services.translation_service import TranslationService, make_provider, timed_call
from app.utils.validators import UserError


class FakeProvider:
    identity = "fake-v1"
    def __init__(self, failures=0):
        self.calls = 0
        self.failures = failures
    def translate(self, text, context):
        self.calls += 1
        assert "fashion" in context
        if self.calls <= self.failures:
            raise ConnectionError("transient")
        return "Phối đồ nam"


def test_success_unicode_cache_and_provider_version(m1):
    settings, sessions, _ = m1
    provider = FakeProvider()
    service = TranslationService(settings, sessions, provider=provider)
    assert service.translate("男生穿搭")[0] == "Phối đồ nam"
    assert service.translate(" 男生穿搭 ")[0] == "Phối đồ nam"
    assert provider.calls == 1
    provider.identity = "fake-v2"
    service.translate("男生穿搭")
    assert provider.calls == 2
    with sessions() as session:
        assert len(list(session.scalars(select(TranslationCache)))) == 2


def test_retry_and_failure_without_fabrication(m1):
    settings, sessions, _ = m1
    sleeps = []
    provider = FakeProvider(failures=2)
    service = TranslationService(settings, sessions, provider=provider, sleep=sleeps.append)
    assert service.translate("男生穿搭")[0] == "Phối đồ nam"
    assert sleeps == [1, 2] and provider.calls == 3
    broken = FakeProvider(failures=10)
    with pytest.raises(UserError, match="sau các lần thử"):
        TranslationService(settings, sessions, provider=broken, sleep=lambda _: None).translate("秋冬")
    assert broken.calls == 3


def test_timeout_no_retry(m1):
    settings, sessions, _ = m1
    provider = FakeProvider()
    def timeout(callback, seconds):
        raise TimeoutError()
    with pytest.raises(UserError, match="thời gian"):
        TranslationService(settings, sessions, provider=provider, call=timeout).translate("男生穿搭")
    assert provider.calls == 0


def test_timed_call_enforces_wait():
    with pytest.raises(TimeoutError):
        timed_call(lambda: time.sleep(.1), .001)


def test_manual_and_non_chinese_do_not_request(m1):
    settings, sessions, _ = m1
    assert TranslationService(settings, sessions).translate("男生穿搭") == ("", "manual")
    provider = FakeProvider()
    assert TranslationService(settings, sessions, provider=provider).translate("ABC 123") == ("", "manual")
    assert provider.calls == 0


def test_missing_argos_and_unknown_provider(m1):
    settings, _, _ = m1
    with pytest.raises(UserError, match="Thiếu mô hình dịch"):
        ArgosProvider(settings.storage_root / "missing")
    settings.translation_provider = "unknown"
    with pytest.raises(UserError):
        make_provider(settings)


def test_curated_fashion_terms_are_exact():
    assert FASHION_TERMS["男生穿搭"] == "Phối đồ nam"
    assert FASHION_TERMS["显高显瘦"] == "Tôn dáng, trông cao và gọn hơn"
