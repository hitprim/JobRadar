import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applicationsApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Badge, Card, CenterLoader, EmptyState, PageError } from "@/components/ui";
import { APPLICATION_STATUS_RU, formatDateTime } from "@/lib/format";
import type { ApplicationStatus } from "@/api/types";

const STATUS_ORDER: ApplicationStatus[] = ["sent", "hr", "tech", "final", "offer", "reject"];

const STATUS_TONE: Record<ApplicationStatus, "neutral" | "good" | "warn" | "bad"> = {
  sent: "neutral",
  hr: "neutral",
  tech: "warn",
  final: "warn",
  offer: "good",
  reject: "bad",
};

export function TrackerPage() {
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const qc = useQueryClient();

  const apps = useQuery({
    queryKey: ["applications", profileId],
    queryFn: () => applicationsApi.list(profileId!),
    enabled: profileId !== null && profileId !== undefined,
  });

  const funnel = useQuery({
    queryKey: ["funnel", profileId],
    queryFn: () => applicationsApi.funnel(profileId!),
    enabled: profileId !== null && profileId !== undefined,
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      applicationsApi.patch(id, { status }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["applications", profileId] });
      void qc.invalidateQueries({ queryKey: ["funnel", profileId] });
    },
  });

  if (!profileId) return null;
  if (apps.isLoading || funnel.isLoading) return <CenterLoader />;
  if (apps.isError) return <PageError message={toApiError(apps.error).detail} />;

  const list = apps.data ?? [];
  const f = funnel.data;

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-semibold">Трекер</h1>

      {/* Funnel */}
      {f && f.total > 0 && (
        <Card>
          <div className="text-sm font-medium mb-2">Воронка (всего {f.total})</div>
          <div className="space-y-1">
            {STATUS_ORDER.map((s) => {
              const count = f.counts[s] ?? 0;
              const pct = Math.round((f.conversion_rates[s] ?? 0) * 100);
              return (
                <div key={s} className="flex items-center gap-2 text-sm">
                  <span className="w-24 text-tg-hint">
                    {APPLICATION_STATUS_RU[s]}
                  </span>
                  <div className="flex-1 bg-tg-bg rounded h-2 overflow-hidden">
                    <div
                      className="h-full bg-tg-link"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="w-12 text-right tabular-nums">{count}</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Applications list */}
      {list.length === 0 ? (
        <EmptyState
          title="Нет откликов"
          hint="Нажмите «Я откликнулся» в карточке вакансии — отклик появится здесь."
        />
      ) : (
        <div className="space-y-3">
          {list.map((a) => (
            <Card key={a.id}>
              <div className="flex items-center justify-between mb-2">
                <Badge tone={STATUS_TONE[a.status]}>
                  {APPLICATION_STATUS_RU[a.status]}
                </Badge>
                <span className="text-xs text-tg-hint">
                  {formatDateTime(a.created_at)}
                </span>
              </div>
              <div className="text-sm text-tg-hint mb-2">
                Вакансия #{a.vacancy_id}
              </div>
              {a.notes && (
                <div className="text-sm bg-tg-bg p-2 rounded mb-2">
                  {a.notes}
                </div>
              )}
              <div className="flex flex-wrap gap-1">
                {STATUS_ORDER.map((s) => (
                  <button
                    key={s}
                    onClick={() => updateStatus.mutate({ id: a.id, status: s })}
                    disabled={a.status === s || updateStatus.isPending}
                    className={`text-xs px-2 py-1 rounded transition-opacity ${
                      a.status === s
                        ? "bg-tg-btn text-tg-btn-text"
                        : "bg-tg-bg text-tg-text border border-tg-secondary-bg hover:opacity-80"
                    } disabled:cursor-not-allowed`}
                  >
                    {APPLICATION_STATUS_RU[s]}
                  </button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
