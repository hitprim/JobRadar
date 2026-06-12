/**
 * Общая форма параметров профиля. Используется и в Onboarding (создание),
 * и в Profile (редактирование) — чтобы поля не расходились между экранами.
 *
 * Контролируемый компонент: держит value-объект и зовёт onChange(patch).
 * Чистая логика (конвертация в payload, валидация) — в @/lib/profileForm.
 */

import { WorkFormatFilter } from "@/components/WorkFormatFilter";
import { ExperiencePicker } from "@/components/ExperiencePicker";
import type { ProfileGrade, Schedule } from "@/api/types";
import type { ProfileFormValue } from "@/lib/profileForm";

const GRADES: { value: ProfileGrade; label: string }[] = [
  { value: "junior", label: "Junior" },
  { value: "middle", label: "Middle" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
];

const SCHEDULES: { value: Schedule; label: string }[] = [
  { value: "fullDay", label: "Полный день" },
  { value: "shift", label: "Сменный" },
  { value: "flexible", label: "Гибкий" },
  { value: "part", label: "Частичная" },
];

interface Props {
  value: ProfileFormValue;
  onChange: (patch: Partial<ProfileFormValue>) => void;
}

export function ProfileForm({ value, onChange }: Props) {
  const toggleSchedule = (s: Schedule) => {
    onChange({
      schedule: value.schedule.includes(s)
        ? value.schedule.filter((x) => x !== s)
        : [...value.schedule, s],
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm mb-1">Название профиля</label>
        <input
          className="input"
          placeholder="Например, Backend"
          value={value.name}
          onChange={(e) => onChange({ name: e.target.value })}
          maxLength={100}
        />
      </div>

      <div>
        <label className="block text-sm mb-1">Стек (через запятую)</label>
        <input
          className="input"
          placeholder="python, fastapi, postgresql"
          value={value.stack}
          onChange={(e) => onChange({ stack: e.target.value })}
        />
      </div>

      <div>
        <label className="block text-sm mb-1">Грейд</label>
        <div className="flex gap-2">
          {GRADES.map((g) => (
            <button
              key={g.value}
              type="button"
              onClick={() => onChange({ grade: g.value })}
              className={`flex-1 py-2 rounded-lg text-sm ${
                value.grade === g.value
                  ? "bg-tg-btn text-tg-btn-text"
                  : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm mb-1">Желаемая ЗП от, ₽</label>
        <input
          className="input"
          type="number"
          inputMode="numeric"
          placeholder="200000"
          value={value.salaryFrom}
          onChange={(e) => onChange({ salaryFrom: e.target.value })}
        />
      </div>

      <WorkFormatFilter
        workFormat={value.workFormat}
        onWorkFormatChange={(workFormat) => onChange({ workFormat })}
        areaIds={value.areaIds}
        onAreaIdsChange={(areaIds) => onChange({ areaIds })}
      />

      <div>
        <label className="block text-sm mb-1">
          График{" "}
          <span className="text-tg-hint">(можно не выбирать — тогда любой)</span>
        </label>
        <div className="flex flex-wrap gap-2">
          {SCHEDULES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => toggleSchedule(s.value)}
              className={`px-3 py-1.5 rounded-full text-sm ${
                value.schedule.includes(s.value)
                  ? "bg-tg-btn text-tg-btn-text"
                  : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <ExperiencePicker
        experience={value.experience}
        onChange={(experience) => onChange({ experience })}
      />

      <div>
        <label className="block text-sm mb-1">
          Стоп-слова{" "}
          <span className="text-tg-hint">(через запятую — что не показывать)</span>
        </label>
        <input
          className="input"
          placeholder="1С, гослото, ночные смены"
          value={value.excludeKeywords}
          onChange={(e) => onChange({ excludeKeywords: e.target.value })}
        />
      </div>
    </div>
  );
}
