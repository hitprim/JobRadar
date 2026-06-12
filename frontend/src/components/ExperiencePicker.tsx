/**
 * Выбор опыта работы (мульти-выбор) — уровни как на hh.ru.
 * Используется в Onboarding и Profile.
 *
 * Это явный фильтр поиска: по выбранным уровням опыта ищем вакансии.
 * Несколько выбранных = ИЛИ. Пусто = не фильтруем по опыту (любой).
 * Опыт отделён от грейда: грейд (junior/middle/...) идёт в LLM-скоринг,
 * а опыт — в фильтр запроса к hh.
 */

import type { Experience } from "@/api/types";

const LEVELS: { value: Experience; label: string }[] = [
  { value: "noExperience", label: "Нет опыта" },
  { value: "between1And3", label: "1–3 года" },
  { value: "between3And6", label: "3–6 лет" },
  { value: "moreThan6", label: "Более 6 лет" },
];

interface Props {
  experience: Experience[];
  onChange: (next: Experience[]) => void;
}

export function ExperiencePicker({ experience, onChange }: Props) {
  const toggle = (e: Experience) => {
    onChange(
      experience.includes(e)
        ? experience.filter((x) => x !== e)
        : [...experience, e],
    );
  };

  return (
    <div>
      <label className="block text-sm mb-1">
        Опыт работы{" "}
        <span className="text-tg-hint">(можно не выбирать — тогда любой)</span>
      </label>
      <div className="flex flex-wrap gap-2">
        {LEVELS.map((l) => (
          <button
            key={l.value}
            type="button"
            onClick={() => toggle(l.value)}
            className={`px-3 py-1.5 rounded-full text-sm ${
              experience.includes(l.value)
                ? "bg-tg-btn text-tg-btn-text"
                : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
            }`}
          >
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}
