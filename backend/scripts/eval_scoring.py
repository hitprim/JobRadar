"""Manual eval промпта скоринга через реальный LLM.

Запуск:
    uv run python -m scripts.eval_scoring

Дёргает OpenRouter на каждом кейсе из tests/eval/golden_dataset.py,
сравнивает score с ожидаемым диапазоном, печатает таблицу результатов.

НЕ запускается в CI — требует валидный OPENROUTER_API_KEY.
"""

from __future__ import annotations

import asyncio
import sys

from src.llm.openrouter import OpenRouterProvider
from src.llm.prompt_loader import load_prompt
from src.llm.scoring import ScoringResult, build_scoring_user_message
from tests.eval.golden_dataset import GOLDEN_CASES, EvalCase


def _evaluate(case: EvalCase, result: ScoringResult) -> tuple[bool, str]:
    low, high = case.score_range
    in_range = low <= result.score <= high
    issues = []
    if not in_range:
        issues.append(f"score {result.score} outside [{low}, {high}]")

    # Проверка red_flag keywords (мягкая)
    for kw in case.must_have_red_flag_keywords:
        if not any(kw.lower() in f.lower() for f in result.red_flags):
            issues.append(f"missing red_flag with '{kw}'")

    for kw in case.must_have_green_flag_keywords:
        if not any(kw.lower() in f.lower() for f in result.green_flags):
            issues.append(f"missing green_flag with '{kw}'")

    return (len(issues) == 0), "; ".join(issues) or "ok"


async def main() -> int:
    provider = OpenRouterProvider()
    passed = 0
    failed = 0

    print(f"{'=' * 80}")
    print(f"{'Case':<45} {'Score':>6} {'Expected':>12} {'Status':>10}")
    print(f"{'-' * 80}")

    for case in GOLDEN_CASES:
        try:
            system = load_prompt("scoring", case.profile.category)
            user = build_scoring_user_message(case.profile, case.vacancy)
            result = await provider.complete(
                system=system, user=user, response_schema=ScoringResult
            )
        except Exception as exc:
            print(f"{case.name:<45} ERROR: {exc}")
            failed += 1
            continue

        ok, msg = _evaluate(case, result)
        expected = f"[{case.score_range[0]}, {case.score_range[1]}]"
        status = "PASS" if ok else "FAIL"
        print(f"{case.name:<45} {result.score:>6} {expected:>12} {status:>10}")
        if not ok:
            print(f"    reason: {result.reason}")
            print(f"    issues: {msg}")
            failed += 1
        else:
            passed += 1

    print(f"{'-' * 80}")
    print(f"Total: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
