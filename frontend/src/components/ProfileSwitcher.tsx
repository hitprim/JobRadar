/**
 * Переключатель профилей. Показывает все активные профили юзера, позволяет
 * сделать любой активным и создать новый.
 *
 * Мульти-профиль: БД и бэкенд поддерживают несколько профилей на юзера.
 * Активный профиль хранится в users.active_profile_id и дублируется в auth-store,
 * откуда его берут Feed / Tracker / Profile.
 */

import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "@/api/endpoints";
import { useAuth } from "@/store/auth";
import { Card, Spinner } from "@/components/ui";
import { toast } from "@/lib/toast";
import { toApiError } from "@/api/client";

export function ProfileSwitcher() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { user, updateUser } = useAuth();
  const activeId = user?.active_profile_id ?? null;

  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesApi.list(),
  });

  const activate = useMutation({
    mutationFn: (id: number) => profilesApi.activate(id),
    onSuccess: (_data, id) => {
      updateUser({ active_profile_id: id });
      // Сбрасываем данные, привязанные к профилю — подтянутся под новый активный.
      void qc.invalidateQueries({ queryKey: ["feed"] });
      void qc.invalidateQueries({ queryKey: ["sources"] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["funnel"] });
      void qc.invalidateQueries({ queryKey: ["profile"] });
      void qc.invalidateQueries({ queryKey: ["resume"] });
      const name = (profiles.data ?? []).find((p) => p.id === id)?.name;
      toast.success(name ? `Профиль: ${name}` : "Профиль переключён");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const list = profiles.data ?? [];
  // Один профиль — переключать нечего, но кнопку «создать» всё равно показываем.

  return (
    <Card className="space-y-2">
      <div className="text-sm font-medium">Профили</div>
      <div className="flex flex-wrap gap-2">
        {profiles.isLoading ? (
          <Spinner size={16} />
        ) : (
          list.map((p) => {
            const isActive = p.id === activeId;
            return (
              <button
                key={p.id}
                type="button"
                disabled={isActive || activate.isPending}
                onClick={() => activate.mutate(p.id)}
                className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-opacity disabled:opacity-100 ${
                  isActive
                    ? "bg-tg-btn text-tg-btn-text"
                    : "bg-tg-bg border border-tg-secondary-bg text-tg-text hover:opacity-80"
                }`}
              >
                {isActive ? "● " : ""}
                {p.name}
              </button>
            );
          })
        )}
        <button
          type="button"
          onClick={() => nav("/profiles/new")}
          className="px-3 py-1.5 rounded-full text-sm whitespace-nowrap bg-tg-bg border border-tg-secondary-bg text-tg-link hover:opacity-80"
        >
          + Новый
        </button>
      </div>
    </Card>
  );
}
