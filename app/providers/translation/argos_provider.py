"""Offline Argos OpenNMT packages, executed directly with CTranslate2.

Captions are short utterances, so no sentence-boundary model is required.
This avoids Argos' document-oriented spaCy/Stanza imports and runtime downloads.
"""
import hashlib
import json
from pathlib import Path

from app.utils.validators import UserError

FASHION_TERMS = {
    "男生穿搭": "Phối đồ nam",
    "显高显瘦": "Tôn dáng, trông cao và gọn hơn",
    "秋冬新款": "Mẫu mới Thu Đông",
    "百搭休闲裤": "Quần casual dễ phối đồ",
}


class ArgosProvider:
    def __init__(self, folder: Path, threads: int = 2, use_glossary: bool = True):
        self.folder, self.threads, self.use_glossary = folder, threads, use_glossary
        self.models = []
        self.packages = []
        for source, target in (("zh", "en"), ("en", "vi")):
            path = folder / f"translate-{source}_{target}-1_9"
            try:
                metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
                if metadata["from_code"] != source or metadata["to_code"] != target:
                    raise ValueError()
                if not (path / "model" / "model.bin").is_file() or not (path / "sentencepiece.model").is_file():
                    raise ValueError()
                self.packages.append((path, metadata))
            except (OSError, ValueError, KeyError) as exc:
                raise UserError("Thiếu mô hình dịch Argos zh→en→vi. Chạy scripts/setup_m1_models.py --translation.") from exc

    @property
    def identity(self) -> str:
        versions = [(m.get("package_version"), m.get("argos_version"), m.get("target_prefix", ""),
                     hashlib.sha256((p / "local-manifest.json").read_bytes()).hexdigest() if (p / "local-manifest.json").is_file() else "unmanifested")
                    for p, m in self.packages]
        digest = hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:16]
        return f"argos-zh-en-vi-1.9-ct2-v1-{digest}-glossary{int(self.use_glossary)}"

    def _load(self):
        if self.models:
            return
        try:
            import ctranslate2
            import sentencepiece
            for path, metadata in self.packages:
                tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(path / "sentencepiece.model"))
                model = ctranslate2.Translator(str(path / "model"), device="cpu", compute_type="int8",
                                              inter_threads=1, intra_threads=self.threads)
                self.models.append((model, tokenizer, metadata.get("target_prefix", "")))
        except Exception as exc:
            raise UserError("Không nạp được mô hình Argos/CTranslate2. Kiểm tra requirements-m1.txt và tệp mô hình.") from exc

    def translate(self, text: str, context: str) -> str:
        if self.use_glossary and text in FASHION_TERMS:
            return FASHION_TERMS[text]
        self._load()
        try:
            for model, tokenizer, prefix in self.models:
                tokens = tokenizer.encode(text, out_type=str)
                if len(tokens) > 256:
                    raise UserError("Đoạn quá dài cho mô hình caption; hãy rút gọn hoặc dịch thủ công.")
                result = model.translate_batch([tokens], target_prefix=[[prefix]] if prefix else None,
                                               beam_size=4, num_hypotheses=1, replace_unknowns=True,
                                               length_penalty=0.2, max_decoding_length=256)
                text = tokenizer.decode(result[0].hypotheses[0]).removeprefix(prefix).replace("▁", " ").replace("_", " ").strip()
            if not text:
                raise ValueError()
            return text
        except UserError:
            raise
        except Exception as exc:
            raise UserError("Mô hình Argos không tạo được bản dịch. Hãy thử lại hoặc nhập bản dịch thủ công.") from exc
