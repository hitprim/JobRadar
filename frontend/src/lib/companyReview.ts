/**
 * Метаданные отзывов о компаниях: RU-подписи сигналов + хелперы respect-score.
 * Чистая логика (без React) — чтобы компоненты экспортировали только компоненты
 * (react-refresh/only-export-components).
 */

import type { CompanyReview } from "@/api/types";

export interface SignalOption {
  value: string;
  label: string;
}

export interface SignalGroup {
  /** Ключ поля в CompanyReview (responded/respect/...). */
  key: "responded" | "respect" | "feedback" | "honesty" | "process";
  /** Вопрос пользователю. */
  question: string;
  /** Варианты от лучшего к худшему. */
  options: [SignalOption, SignalOption, SignalOption];
}

export const SIGNAL_GROUPS: SignalGroup[] = [
  {
    key: "responded",
    question: "Ответили ли на отклик?",
    options: [
      { value: "fast", label: "Быстро ответили" },
      { value: "slow", label: "Долго молчали" },
      { value: "ignored", label: "Проигнорировали" },
    ],
  },
  {
    key: "respect",
    question: "Как общались?",
    options: [
      { value: "respectful", label: "Уважительно" },
      { value: "neutral", label: "Нейтрально" },
      { value: "dismissive", label: "Пренебрежительно" },
    ],
  },
  {
    key: "feedback",
    question: "Дали обратную связь?",
    options: [
      { value: "detailed", label: "Развёрнутую" },
      { value: "formal", label: "Формальную отписку" },
      { value: "none", label: "Без ответа" },
    ],
  },
  {
    key: "honesty",
    question: "Вакансия совпала с реальностью?",
    options: [
      { value: "matched", label: "Всё совпало" },
      { value: "minor", label: "Мелкие расхождения" },
      { value: "mismatch", label: "Обманули" },
    ],
  },
  {
    key: "process",
    question: "Каким был процесс?",
    options: [
      { value: "smooth", label: "Комфортным" },
      { value: "tolerable", label: "Терпимым" },
      { value: "draining", label: "Изматывающим" },
    ],
  },
];

/** Человекочитаемая подпись выбранного значения сигнала. */
export function signalLabel(
  key: SignalGroup["key"],
  value: string,
): string {
  const group = SIGNAL_GROUPS.find((g) => g.key === key);
  return group?.options.find((o) => o.value === value)?.label ?? value;
}

/** Все подписи одного отзыва (для компактного отображения). */
export function reviewSignalLabels(review: CompanyReview): string[] {
  return SIGNAL_GROUPS.map((g) => signalLabel(g.key, review[g.key]));
}

/** Тон бейджа respect-score (та же шкала, что и у скоринга). */
export function respectTone(
  score: number | null,
): "good" | "warn" | "bad" | "neutral" {
  if (score === null) return "neutral";
  if (score >= 67) return "good";
  if (score >= 34) return "warn";
  return "bad";
}

/** Короткая словесная оценка отношения компании. */
export function respectWord(score: number | null): string {
  if (score === null) return "Нет отзывов";
  if (score >= 67) return "Уважают";
  if (score >= 34) return "По-разному";
  return "Не уважают";
}
