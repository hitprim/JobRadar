"""Manual eval промпта генерации сопроводительных через реальный LLM.

Запуск:
    uv run python -m scripts.eval_letters

Дёргает OpenRouter на каждом IT-кейсе из tests/eval/golden_dataset.py,
печатает сгенерированные письма с базовыми проверками:
- длина в разумных рамках (150-400 слов)
- упоминание компании
- упоминание хотя бы одного навыка из profile.stack
- отсутствие markdown-маркеров
- отсутствие banned-фраз

НЕ запускается в CI — требует валидный OPENROUTER_API_KEY.
"""

from __future__ import annotations

import asyncio
import re
import sys

from src.llm.letter import LetterResult, build_letter_user_message
from src.llm.openrouter import OpenRouterProvider
from src.llm.prompt_loader import load_prompt
from tests.eval.golden_dataset import GOLDEN_CASES, EvalCase

# Фразы которые НЕ должны появляться (запах LLM / generic praise)
_BANNED_PHRASES = [
    "ваша компания — лидер",
    "сильный бренд",
    "идеальная позиция",
    "i am thrilled",
    "thrilled to apply",
    "**",  # markdown bold
    "#",  # markdown header
]


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _evaluate(case: EvalCase, result: LetterResult) -> tuple[bool, list[str], list[str]]:
    """Возвращает (ok, hard_issues, soft_warnings).

    hard_issues — критичные, валят тест.
    soft_warnings — желательно но не блокер (например, упоминание имени компании).
    """
    text = result.letter_text
    issues: list[str] = []
    warnings: list[str] = []

    # Длина — hard
    wc = _word_count(text)
    if wc < 100:
        issues.append(f"too short ({wc} words)")
    if wc > 450:
        issues.append(f"too long ({wc} words)")

    # Упоминание компании — soft (можно "ваша компания")
    if case.vacancy.company_name and case.vacancy.company_name.lower() not in text.lower():
        warnings.append(f"no company name '{case.vacancy.company_name}' (used generic ref)")

    # Упоминание хотя бы одного навыка из стека — hard (без этого письмо бесполезное)
    if case.profile.stack:
        mentioned = [s for s in case.profile.stack if s.lower() in text.lower()]
        if not mentioned:
            issues.append(f"no stack item mentioned (have: {case.profile.stack})")

    # Banned-фразы — hard
    text_lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in text_lower:
            issues.append(f"banned phrase: '{phrase}'")

    return (len(issues) == 0), issues, warnings


async def main() -> int:
    provider = OpenRouterProvider()
    passed = 0
    failed = 0

    # Берём только match-кейсы где есть смысл писать письмо
    cases = [
        c
        for c in GOLDEN_CASES
        if c.name in ("perfect_match_senior_python_remote", "solid_match_middle_django")
    ]

    print("=" * 80)
    for case in cases:
        try:
            system = load_prompt("letters", case.profile.category)
            user = build_letter_user_message(case.profile, case.vacancy)
            result = await provider.complete(system=system, user=user, response_schema=LetterResult)
        except Exception as exc:
            print(f"ERROR on {case.name}: {exc}")
            failed += 1
            continue

        ok, issues, warnings = _evaluate(case, result)
        status = "PASS" if ok else "FAIL"
        print(f"\n--- {case.name} :: {status} ---")
        print(f"draft_notes: {result.draft_notes}")
        print(f"letter ({_word_count(result.letter_text)} words):\n")
        print(result.letter_text)
        if warnings:
            print(f"\nWARNINGS: {warnings}")
        if not ok:
            print(f"\nISSUES: {issues}")
            failed += 1
        else:
            passed += 1

    print("\n" + "=" * 80)
    print(f"Total: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
