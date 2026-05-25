import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sourcesApi, vacanciesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, CenterLoader, EmptyState, PageError } from "@/components/ui";
import { VacancyCard } from "@/components/VacancyCard";

export function FeedPage() {
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const qc = useQueryClient();

  const feed = useQuery({
    queryKey: ["feed", profileId],
    queryFn: () => vacanciesApi.feed(profileId!),
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
      // В v0.1 один источник на профиль, но рефрешим все на всякий
      await Promise.all(list.map((s) => sourcesApi.refresh(s.id)));
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["feed", profileId] });
      void qc.invalidateQueries({ queryKey: ["sources", profileId] });
    },
  });

  if (!profileId) return null;
  if (feed.isLoading) return <CenterLoader />;
  if (feed.isError) return <PageError message={toApiError(feed.error).detail} />;

  const items = feed.data ?? [];

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Лента</h1>
        <Button
          variant="secondary"
          loading={refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          ⟳ Обновить
        </Button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="Пока пусто"
          hint="Нажмите «Обновить» — мы поищем свежие вакансии под ваш профиль."
        />
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
