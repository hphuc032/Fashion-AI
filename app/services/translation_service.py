"""Provider selection, persistent versioned cache and bounded retries."""
import hashlib
import json
import threading
import time

from sqlalchemy.dialects.sqlite import insert

from app.core.config import Settings
from app.database.m1_models import TranslationCache
from app.providers.translation.argos_provider import ArgosProvider
from app.services.text_tracker import contains_chinese, normalized
from app.utils.validators import UserError

CONTEXT = "Chinese men's fashion captions to concise faithful Vietnamese; preserve brands and identifiers; do not invent claims."


def make_provider(settings: Settings):
    if settings.translation_provider == "manual":
        return None
    if settings.translation_provider == "argos":
        return ArgosProvider(settings.argos_models_dir or settings.storage_root / "models" / "argos",
                             settings.ocr_cpu_threads)
    raise UserError("Nhà cung cấp dịch không được hỗ trợ. Chọn manual hoặc argos.")


def timed_call(callback, timeout: float):
    """Bound UI/job wait; worker is a disposable process if native inference stalls.

    A daemon thread cannot block process exit. Never retry after a timeout, to
    avoid overlapping inference on a model instance. The job supervisor ends it.
    """
    result = []
    error = []

    def invoke():
        try:
            result.append(callback())
        except Exception as exc:
            error.append(exc)

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("Translation time limit exceeded")
    if error:
        raise error[0]
    return result[0]


class TranslationService:
    def __init__(self, settings, sessions, provider=None, sleep=time.sleep, call=timed_call):
        self.settings, self.sessions = settings, sessions
        self.provider = provider if provider is not None else make_provider(settings)
        self.sleep, self.call = sleep, call

    def translate(self, text: str, check_cancel=lambda: None) -> tuple[str, str]:
        text = normalized(text)
        if not contains_chinese(text) or self.provider is None:
            return "", "manual"
        if len(text) > 1000:
            raise UserError("Đoạn quá dài; hãy dịch thủ công.")
        identity = self.provider.identity
        key = hashlib.sha256(json.dumps([identity, "zh", "vi", text, CONTEXT], ensure_ascii=False).encode()).hexdigest()
        with self.sessions() as session:
            cached = session.get(TranslationCache, key)
            if cached:
                return cached.translated_text, identity
        for attempt in range(self.settings.translation_retries + 1):
            check_cancel()
            try:
                translated = self.call(lambda: self.provider.translate(text, CONTEXT), self.settings.translation_timeout_seconds)
                if not isinstance(translated, str) or not translated.strip():
                    raise ValueError("empty translation")
                translated = translated.strip()
                check_cancel()
                with self.sessions.begin() as session:
                    session.execute(insert(TranslationCache).values(key=key, provider=identity, translated_text=translated)
                                    .on_conflict_do_nothing(index_elements=["key"]))
                return translated, identity
            except TimeoutError as exc:
                raise UserError("Dịch quá thời gian chờ; hãy thử lại hoặc dịch thủ công.") from exc
            except UserError:
                # Configuration/model errors are not transient; do not repeatedly load broken models.
                raise
            except Exception as exc:
                if attempt == self.settings.translation_retries:
                    raise UserError("Nhà cung cấp dịch gặp lỗi sau các lần thử. Hãy thử lại hoặc dịch thủ công.") from exc
                self.sleep(min(2 ** attempt, 4))
        raise AssertionError("unreachable")
