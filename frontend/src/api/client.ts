/**
 * Axios-инстанс с auto-attach JWT из Zustand auth-store и логаутом при 401.
 */

import axios, { AxiosError } from "axios";
import { useAuth } from "@/store/auth";

/**
 * Базовый URL backend API.
 *
 * - В dev (Vite proxy): `/api` → vite.config проксирует на http://localhost:8000.
 * - В prod: build с `VITE_API_BASE_URL=https://...railway.app/api`.
 *   Cloudflare Pages env-переменная задаётся в Project Settings → Environment.
 */
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/+$/, "");

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  const token = useAuth.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    // 401 → токен невалиден / истёк → разлогиниваем
    if (error.response?.status === 401) {
      const { token, logout } = useAuth.getState();
      if (token) {
        logout();
        // редирект не делаем — Router увидит token=null и покажет Onboarding
      }
    }
    return Promise.reject(error);
  },
);

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err) && err.response) {
    const detail = (err.response.data as { detail?: string })?.detail ?? err.message;
    return new ApiError(err.response.status, detail);
  }
  return new ApiError(0, err instanceof Error ? err.message : "Unknown error");
}
