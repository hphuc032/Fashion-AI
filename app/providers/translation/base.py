from typing import Protocol


class Translator(Protocol):
    @property
    def identity(self) -> str: ...

    def translate(self, text: str, context: str) -> str: ...
