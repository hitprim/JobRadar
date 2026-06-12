import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sourcesApi, vacanciesApi, type FeedFilter } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, EmptyState, PageError, SkeletonCard } from "@/components/ui";
import { VacancyCard } from "@/components/VacancyCard";
import { toast } from "@/lib/toast";

// undefined-вкладка = «Все» (бэкенд прячет пропущенные). like/save — фильтр по реакции.
const TABS: { key: FeedFilter | undefined; label: string }[] = [
  { key: undefined, label: "Все" },
  { key: "like", label: "👍 Нравятся" },
  { key: "save", label: "⭐ Избранное" },
];

const EMPTY: Record<string, { title: string; hint: string }> = {
  active: {
    title: "Пока пусто",
    hint: "Нажмите «Обновить» — мы поищем свежие вакансии под ваш профиль.",
  },
  like: {
    title: "Нет понравившихся",
    hint: "Откройте вакансию и нажмите 👍 «Нравится» — она появится здесь.",
  },
  save: {
    title: "Избранное пусто",
    hint: "Сохраняйте вакансии кнопкой ⭐ «В избранное», чтобы вернуться к ним позже.",
  },
};

export function FeedPage() {
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const qc = useQueryClient();
  const [started, setStarted] = useState(false);
  const [view, setView] = useState<FeedFilter | undefined>(undefined);

  const feed = useQuery({
    queryKey: ["feed", profileId, view ?? "active"],
    queryFn: () => vacanciesApi.feed(profileId!, view ? { reaction: view } : undefined),
    enabled: profileId !== null && profileId !== undefined,
  });

  const sources = useQuery({
    queryKey: ["sources", profileId],
    queryFn: () => sourcesApi.list(profileId!),
    enabled: profileId !== null && profileId !== undefined,
  });

  const refresh = useMutation({
    mutationFn: async () => {
      const list = sources.data ?? [];
      // В v0.1 один источник на профиль, но рефрешим все на всякий.
      // Эндпоинт возвращается сразу (202) — парсинг идёт в фоне, итог придёт
      // пушем в Telegram.
      await Promise.all(list.map((s) => sourcesApi.refresh(s.id)));
    },
    onSuccess: () => {
      setStarted(true);
      toast.info("Ищем свежие вакансии…");
      // Парсинг hh.ru через Chrome занимает ~40-60с. Подтянем ленту с запасом,
      // чтобы новые вакансии появились без ручной перезагрузки.
      window.setTimeout(() => {
        void qc.invalidateQueries({ queryKey: ["feed", profileId] });
        void qc.invalidateQueries({ queryKey: ["sources", profileId] });
        setStarted(false);
      }, 60_000);
    },
  });

  if (!profileId) return null;

  const items = feed.data ?? [];
  const emptyKey = view ?? "active";

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Лента</h1>
        <Button
          variant="secondary"
          loading={refresh.isPending}
          disabled={started}
          onClick={() => refresh.mutate()}
        >
          ⟳ Обновить
        </Button>
      </div>

      {/* Вкладки-фильтры по реакции */}
      <div className="flex gap-2 mb-4">
        {TABS.map((t) => (
          <button
            key={t.label}
            onClick={() => setView(t.key)}
            className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-opacity ${
              view === t.key
                ? "bg-tg-btn text-tg-btn-text"
                : "bg-tg-secondary-bg text-tg-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {started && (
        <div className="mb-4 rounded-lg bg-tg-secondary-bg p-3 text-sm text-tg-text">
          🔎 Ищем свежие вакансии под ваш профиль. Это занимает до минуты —
          пришлём результат в Telegram и обновим ленту автоматически.
        </div>
      )}

      {feed.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : feed.isError ? (
        <PageError message={toApiError(feed.error).detail} />
      ) : items.length === 0 ? (
        <EmptyState title={EMPTY[emptyKey].title} hint={EMPTY[emptyKey].hint} />
      ) : (
        <div className="space-y-3">
          {items.map((it) => (
            <VacancyCard key={it.vacancy.id} item={it} />
          ))}
        </div>
      )}
    </div>
  );
}
