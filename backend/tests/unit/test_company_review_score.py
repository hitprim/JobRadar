"""Unit-тесты чистой логики отзывов: respect-score и company_key."""

from __future__ import annotations

from src.domain.company_review import company_key_for, compute_review_score


class TestComputeReviewScore:
    def test_all_best_is_100(self) -> None:
        assert compute_review_score("fast", "respectful", "detailed", "matched", "smooth") == 100

    def test_all_worst_is_0(self) -> None:
        assert compute_review_score("ignored", "dismissive", "none", "mismatch", "draining") == 0

    def test_all_neutral_is_50(self) -> None:
        assert compute_review_score("slow", "neutral", "formal", "minor", "tolerable") == 50

    def test_responded_and_respect_weigh_more(self) -> None:
        # Игнор + пренебрежение (вес 0.6) сильнее бьёт по score, чем
        # три «лёгких» сигнала в ноль (вес 0.4) при прочих равных.
        ignored_respect = compute_review_score(
            "ignored", "dismissive", "detailed", "matched", "smooth"
        )
        weak_signals = compute_review_score(
            "fast", "respectful", "none", "mismatch", "draining"
        )
        assert ignored_respect < weak_signals


class TestCompanyKey:
    def test_prefers_company_id(self) -> None:
        assert company_key_for("12345", "ООО Ромашка") == "id:12345"

    def test_falls_back_to_normalized_name(self) -> None:
        assert company_key_for(None, "  Acme   Corp  ") == "name:acme corp"

    def test_name_case_insensitive(self) -> None:
        assert company_key_for(None, "ACME") == company_key_for(None, "acme")

    def test_none_when_nothing(self) -> None:
        assert company_key_for(None, None) is None
        assert company_key_for("", "") is None
        assert company_key_for("  ", "  ") is None
