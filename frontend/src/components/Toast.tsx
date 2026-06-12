/**
 * <Toaster/> — рендер очереди тостов. Монтируется один раз в корне (main.tsx).
 * Логика стора и хелпер `toast` — в @/lib/toast.
 */

import { useEffect } from "react";
import { useToastStore, type ToastItem, type ToastTone } from "@/lib/toast";

const TONE_CLASS: Record<ToastTone, string> = {
  success: "bg-green-600 text-white",
  error: "bg-red-600 text-white",
  info: "bg-tg-secondary-bg text-tg-text",
};

const TONE_ICON: Record<ToastTone, string> = {
  success: "✓",
  error: "✕",
  info: "•",
};

function ToastRow({ item }: { item: ToastItem }) {
  const remove = useToastStore((s) => s.remove);
  useEffect(() => {
    const t = setTimeout(() => remove(item.id), 2500);
    return () => clearTimeout(t);
  }, [item.id, remove]);

  return (
    <div
      onClick={() => remove(item.id)}
      className={`pointer-events-auto flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium shadow-lg ${TONE_CLASS[item.tone]}`}
    >
      <span>{TONE_ICON[item.tone]}</span>
      <span className="flex-1">{item.message}</span>
    </div>
  );
}

export function Toaster() {
  const items = useToastStore((s) => s.items);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4">
      {items.map((item) => (
        <ToastRow key={item.id} item={item} />
      ))}
    </div>
  );
}
