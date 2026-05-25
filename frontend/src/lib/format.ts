/**
 * Форматтеры. Без localization library — это i18n v0.3.
 */

export function formatSalary(
  from: number | null,
  to: number | null,
  currency: string | null,
): string {
  if (from === null && to === null) return "Не указана";
  const cur = currency ?? "RUR";
  const sym = cur === "RUR" || cur === "RUB" ? "₽" : cur;
  const fmt = (n: number) => n.toLocaleString("ru-RU");
  if (from !== null && to !== null) return `${fmt(from)} – ${fmt(to)} ${sym}`;
  if (from !== null) return `от ${fmt(from)} ${sym}`;
  return `до ${fmt(to!)} ${sym}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function scoreTone(score: number | null): "good" | "warn" | "bad" | "neutral" {
  if (score === null) return "neutral";
  if (score >= 70) return "good";
  if (score >= 40) return "warn";
  return "bad";
}

export const APPLICATION_STATUS_RU: Record<string, string> = {
  sent: "Отправлено",
  hr: "HR",
  tech: "Тех. интервью",
  final: "Финал",
  offer: "Оффер",
  reject: "Отказ",
};
