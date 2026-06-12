/**
 * Гибкий выбор формата работы (мульти-выбор) + город при выборе офиса/гибрида.
 * Используется в Onboarding и Profile.
 *
 * work_format — массив: юзер может выбрать и удалёнку, и офис одновременно.
 * Город нужен только если выбран office или hybrid (для удалёнки регион не важен).
 */

import { CITIES } from "@/lib/cities";
import type { WorkFormat } from "@/api/types";

const FORMATS: { value: WorkFormat; label: string }[] = [
  { value: "remote", label: "Удалёнка" },
  { value: "hybrid", label: "Гибрид" },
  { value: "office", label: "Офис" },
];

interface Props {
  workFormat: WorkFormat[];
  onWorkFormatChange: (next: WorkFormat[]) => void;
  areaIds: number[];
  onAreaIdsChange: (next: number[]) => void;
}

export function WorkFormatFilter({
  workFormat,
  onWorkFormatChange,
  areaIds,
  onAreaIdsChange,
}: Props) {
  const needsCity = workFormat.includes("office") || workFormat.includes("hybrid");

  const toggleFormat = (f: WorkFormat) => {
    onWorkFormatChange(
      workFormat.includes(f)
        ? workFormat.filter((x) => x !== f)
        : [...workFormat, f],
    );
  };

  const toggleCity = (id: number) => {
    onAreaIdsChange(
      areaIds.includes(id)
        ? areaIds.filter((x) => x !== id)
        : [...areaIds, id],
    );
  };

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm mb-1">Формат работы</label>
        <div className="flex gap-2">
          {FORMATS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => toggleFormat(f.value)}
              className={`flex-1 py-2 rounded-lg text-sm ${
                workFormat.includes(f.value)
                  ? "bg-tg-btn text-tg-btn-text"
                  : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {needsCity && (
        <div>
          <label className="block text-sm mb-1">
            Город{" "}
            <span className="text-tg-hint">(для офиса / гибрида)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            {CITIES.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleCity(c.id)}
                className={`px-3 py-1.5 rounded-full text-sm ${
                  areaIds.includes(c.id)
                    ? "bg-tg-btn text-tg-btn-text"
                    : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
