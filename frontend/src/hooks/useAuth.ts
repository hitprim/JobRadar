/**
 * Auth-flow: при монтировании пытается войти через Telegram WebApp initData,
 * fallback на dev-endpoint в browser-mode.
 */

import { useEffect, useState } from "react";
import { useAuth } from "@/store/auth";
import { authApi } from "@/api/endpoints";
import { applyTelegramTheme, getTelegram } from "@/lib/telegram";
import { toApiError } from "@/api/client";

export type AuthStatus = "idle" | "loading" | "ready" | "error";

export function useBootstrapAuth(): { status: AuthStatus; error: string | null } {
  const { token, setSession } = useAuth();
  const [status, setStatus] = useState<AuthStatus>(token ? "ready" : "loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) {
      setStatus("ready");
      return;
    }

    let cancelled = false;
    const run = async () => {
      setStatus("loading");
      try {
        const tg = getTelegram();
        if (tg) {
          applyTelegramTheme(tg);
          tg.ready();
          tg.expand();
          const res = await authApi.telegram(tg.initData);
          if (!cancelled) setSession(res.access_token, res.user);
        } else {
          // Dev-режим в обычном браузере
          const res = await authApi.dev();
          if (!cancelled) setSession(res.access_token, res.user);
        }
        if (!cancelled) setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        const e = toApiError(err);
        setError(e.detail);
        setStatus("error");
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [token, setSession]);

  return { status, error };
}
