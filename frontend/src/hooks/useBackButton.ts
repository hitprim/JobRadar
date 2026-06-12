/**
 * Регистрирует обработчик нативной кнопки «Назад» Telegram, пока active=true.
 *
 * handler может меняться между рендерами — храним его в ref, чтобы не
 * перерегистрировать стек на каждый рендер.
 */

import { useEffect, useRef } from "react";
import { pushBackHandler } from "@/lib/backButton";

export function useBackButton(handler: () => void, active = true): void {
  const ref = useRef(handler);
  ref.current = handler;

  useEffect(() => {
    if (!active) return;
    return pushBackHandler(() => ref.current());
  }, [active]);
}
