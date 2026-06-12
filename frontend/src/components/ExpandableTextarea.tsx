/**
 * Textarea с кнопкой «развернуть на весь экран».
 *
 * Зачем: читать длинный текст в маленьком поле удобно, а редактировать —
 * нет. Кнопка ⛶ открывает полноэкранный редактор поверх всего. Нативная
 * кнопка «Назад» Telegram (и системная на телефоне) закрывают редактор,
 * а не уводят с экрана — через useBackButton.
 */

import { useEffect, useState } from "react";
import { useBackButton } from "@/hooks/useBackButton";

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
  /** Высота свёрнутого поля, напр. "min-h-[300px]". */
  minHeightClass?: string;
  /** Заголовок полноэкранного редактора. */
  title?: string;
  className?: string;
}

export function ExpandableTextarea({
  value,
  onChange,
  placeholder,
  maxLength,
  minHeightClass = "min-h-[200px]",
  title = "Редактирование",
  className = "",
}: Props) {
  const [full, setFull] = useState(false);
  useBackButton(() => setFull(false), full);

  // Блокируем прокрутку фона, пока открыт полноэкранный редактор.
  useEffect(() => {
    if (!full) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [full]);

  return (
    <div className={`relative ${className}`}>
      <textarea
        className={`input ${minHeightClass} text-sm leading-relaxed pr-10`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
      />
      <button
        type="button"
        onClick={() => setFull(true)}
        aria-label="Открыть на весь экран"
        title="На весь экран"
        className="absolute top-2 right-2 rounded-md bg-tg-bg/70 px-1.5 py-0.5 text-base leading-none text-tg-hint hover:text-tg-text"
      >
        ⛶
      </button>

      {full && (
        <div className="fixed inset-0 z-50 flex flex-col bg-tg-bg">
          <div className="flex items-center justify-between border-b border-tg-secondary-bg p-3">
            <button onClick={() => setFull(false)} className="btn-ghost -ml-2">
              ← Назад
            </button>
            <span className="truncate px-2 text-sm font-medium">{title}</span>
            <button onClick={() => setFull(false)} className="btn-ghost font-medium">
              Готово
            </button>
          </div>
          <textarea
            autoFocus
            className="flex-1 w-full resize-none bg-tg-bg p-4 text-base leading-relaxed text-tg-text focus:outline-none"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            maxLength={maxLength}
          />
          <div className="border-t border-tg-secondary-bg px-4 py-2 text-xs text-tg-hint">
            {value.length}
            {maxLength != null ? ` / ${maxLength}` : ""} символов
          </div>
        </div>
      )}
    </div>
  );
}
