/**
 * Стор тостов + хелпер `toast`. Отделён от компонента <Toaster/>, чтобы
 * react-refresh не ругался на смешанные экспорты (компонент + функции).
 */

import { create } from "zustand";
import { haptic } from "@/lib/telegram";

export type ToastTone = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastState {
  items: ToastItem[];
  push: (message: string, tone: ToastTone) => void;
  remove: (id: number) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (message, tone) =>
    set((s) => ({ items: [...s.items, { id: Date.now() + Math.random(), message, tone }] })),
  remove: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

export const toast = {
  success: (message: string) => {
    haptic("light");
    useToastStore.getState().push(message, "success");
  },
  error: (message: string) => {
    haptic("heavy");
    useToastStore.getState().push(message, "error");
  },
  info: (message: string) => {
    useToastStore.getState().push(message, "info");
  },
};
