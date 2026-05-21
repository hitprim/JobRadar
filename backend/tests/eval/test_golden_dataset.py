"""CI-тесты golden dataset.

БЕЗ вызова LLM. Проверяет:
- датасет валидный (профили/вакансии можно построить, score_range разумный)
- prompt builder работает на каждом кейсе без ошибок
- защита от injection не ломается на реальных данных

Реальная eval LLM — отдельным скриптом scripts/eval_scoring.py, в CI не запускается.
"""

from __future__ import annotations

import pytest

from src.llm.scoring import build_scoring_user_message
from tests.eval.golden_dataset import GOLDEN_CASES, EvalCase


class TestGoldenDatasetValidity:
    def test_dataset_not_empty(self) -> None:
        assert len(GOLDEN_CASES) >= 5

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
    def test_case_score_range_sane(self, case: EvalCase) -> None:
        low, high = case.score_range
        assert 0 <= low <= high <= 100
        # Range не должен быть слишком узким (отказоустойчивость промпта)
        assert high - low >= 15, f"range too narrow for {case.name}"

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
    def test_prompt_builds_on_case(self, case: EvalCase) -> None:
        msg = build_scoring_user_message(case.profile, case.vacancy)
        assert "<user_input>" in msg
        assert "</user_input>" in msg
        # Только один экземпляр закрывающего тега — наш собственный
        assert msg.count("</user_input>") == 1
        # Базовая структура присутствует
        assert "<profile>" in msg
        assert "<vacancy>" in msg

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
    def test_case_names_unique(self, case: EvalCase) -> None:  # noqa: ARG002
        names = [c.name for c in GOLDEN_CASES]
        assert len(names) == len(set(names))
