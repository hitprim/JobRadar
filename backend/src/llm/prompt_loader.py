"""Загрузка markdown-промптов из src/llm/prompts/.

Структура:
    prompts/
        scoring/
            default.md
            it.md
            finance.md (v0.2)
        letters/
            default.md
            it.md
        classification/
            detect_category.md

`load_prompt(kind, category)` возвращает содержимое нужного файла.
Если файла для категории нет — fallback на default.md.
Кэшируется через lru_cache (промпты — статика, не меняются в рантайме).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

# Корень каталога promts — src/llm/prompts/
_PROMPTS_ROOT = Path(__file__).parent / "prompts"

PromptKind = Literal["scoring", "letters", "classification"]


class PromptNotFoundError(FileNotFoundError):
    """Не нашли ни category-промпт, ни default.md."""


@lru_cache(maxsize=128)
def load_prompt(kind: PromptKind, category: str) -> str:
    """Возвращает текст промпта.

    Сначала ищет `prompts/{kind}/{category}.md`, затем `prompts/{kind}/default.md`.
    Бросает PromptNotFoundError если оба отсутствуют.
    """
    base = _PROMPTS_ROOT / kind
    specific = base / f"{category}.md"
    default = base / "default.md"
    target = specific if specific.is_file() else default
    if not target.is_file():
        raise PromptNotFoundError(
            f"No prompt found for kind={kind} category={category}: tried {specific} and {default}"
        )
    return target.read_text(encoding="utf-8")
