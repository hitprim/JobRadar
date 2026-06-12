/**
 * Wrapper над Telegram WebApp API.
 *
 * Грузим скрипт через index.html (window.Telegram.WebApp). Если запущено вне
 * Telegram (обычный браузер) — возвращаем null, фронт переключается на dev-auth.
 */

export interface TgBackButton {
  isVisible: boolean;
  show: () => void;
  hide: () => void;
  onClick: (cb: () => void) => void;
  offClick: (cb: () => void) => void;
}

export interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name?: string; username?: string } };
  themeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
    secondary_bg_color?: string;
    destructive_text_color?: string;
  };
  colorScheme: "light" | "dark";
  ready: () => void;
  expand: () => void;
  HapticFeedback?: { impactOccurred: (style: "light" | "medium" | "heavy") => void };
  BackButton?: TgBackButton;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export function getTelegram(): TgWebApp | null {
  const tg = window.Telegram?.WebApp;
  // initData пустой → запущено вне Telegram (debug в браузере)
  if (!tg || !tg.initData) return null;
  return tg;
}

export function applyTelegramTheme(tg: TgWebApp): void {
  const root = document.documentElement;
  const t = tg.themeParams;
  if (t.bg_color) root.style.setProperty("--tg-bg", t.bg_color);
  if (t.text_color) root.style.setProperty("--tg-text", t.text_color);
  if (t.hint_color) root.style.setProperty("--tg-hint", t.hint_color);
  if (t.link_color) root.style.setProperty("--tg-link", t.link_color);
  if (t.button_color) root.style.setProperty("--tg-btn", t.button_color);
  if (t.button_text_color) root.style.setProperty("--tg-btn-text", t.button_text_color);
  if (t.secondary_bg_color) root.style.setProperty("--tg-secondary-bg", t.secondary_bg_color);
  if (t.destructive_text_color) root.style.setProperty("--tg-destructive", t.destructive_text_color);
  document.body.dataset.theme = tg.colorScheme;
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  getTelegram()?.HapticFeedback?.impactOccurred(style);
}
