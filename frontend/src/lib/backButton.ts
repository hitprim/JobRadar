/**
 * Менеджер аппаратной/нативной кнопки «Назад» Telegram WebApp.
 *
 * Зачем: по умолчанию системная кнопка «Назад» на телефоне закрывает MiniApp.
 * Telegram даёт BackButton API — если кнопка показана, системный «Назад»
 * отдаётся ей, а не закрывает приложение.
 *
 * Поддерживаем СТЕК обработчиков: верхний в стеке — активный. Это позволяет
 * вложенность (например, открытый полноэкранный редактор перехватывает «Назад»,
 * чтобы закрыться, а не уводить с экрана). Когда стек пуст — кнопка скрыта,
 * и системный «Назад» снова закрывает MiniApp (ожидаемо на верхних вкладках).
 */

import { getTelegram } from "./telegram";

type Handler = () => void;

const stack: Handler[] = [];
let bound: Handler | null = null;

function sync(): void {
  const bb = getTelegram()?.BackButton;
  if (!bb) return; // вне Telegram (dev в браузере) — no-op

  if (bound) {
    bb.offClick(bound);
    bound = null;
  }

  const top = stack[stack.length - 1];
  if (top) {
    bound = top;
    bb.onClick(bound);
    bb.show();
  } else {
    bb.hide();
  }
}

/** Кладёт обработчик на вершину стека. Возвращает функцию снятия. */
export function pushBackHandler(handler: Handler): () => void {
  stack.push(handler);
  sync();
  return () => {
    const i = stack.lastIndexOf(handler);
    if (i !== -1) stack.splice(i, 1);
    sync();
  };
}
