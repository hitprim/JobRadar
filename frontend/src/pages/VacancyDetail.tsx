import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applicationsApi, vacanciesApi } from "@/api/endpoints";
import { ApiError, toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Badge, Button, Card, CenterLoader, PageError } from "@/components/ui";
import { formatDate, formatSalary, scoreTone } from "@/lib/format";
import { haptic } from "@/lib/telegram";

export function VacancyDetailPage() {
  const { id: idStr } = useParams<{ id: string }>();
  const vacancyId = Number(idStr);
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const nav = useNavigate();
  const qc = useQueryClient();

  const vacancy = useQuery({
    queryKey: ["vacancy", vacancyId],
    queryFn: () => vacanciesApi.get(vacancyId),
    enabled: Number.isFinite(vacancyId),
  });

  const feed = useQuery({
    queryKey: ["feed", profileId],
    queryFn: () => vacanciesApi.feed(profileId!),
    enabled: profileId !== null && profileId !== undefined,
  });

  const score = useMutation({
    mutationFn: () => vacanciesApi.score(vacancyId, profileId!),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["feed", profileId] }),
  });

  const react = useMutation({
    mutationFn: (r: "like" | "skip" | "save") =>
      vacanciesApi.react(vacancyId, profileId!, r),
    onSuccess: () => {
      haptic("light");
      void qc.invalidateQueries({ queryKey: ["feed", profileId] });
    },
  });

  const apply = useMutation({
    mutationFn: () => applicationsApi.create(profileId!, { vacancy_id: vacancyId }),
    onSuccess: (app) => {
      void qc.invalidateQueries({ queryKey: ["applications", profileId] });
      nav(`/tracker?application=${app.id}`);
    },
  });

  if (vacancy.isLoading) return <CenterLoader />;
  if (vacancy.isError) return <PageError message={toApiError(vacancy.error).detail} />;
  if (!vacancy.data) return null;
  const v = vacancy.data;

  // Реакция / score для текущего профиля — из feed
  const feedItem = (feed.data ?? []).find((i) => i.vacancy.id === vacancyId);
  const cachedScore = feedItem?.reaction?.score ?? null;

  const applyExistingId =
    apply.error instanceof ApiError && apply.error.status === 409
      ? apply.error.detail.match(/id=(\d+)/)?.[1]
      : null;

  return (
    <div className="p-4 space-y-4">
      <button onClick={() => nav(-1)} className="btn-ghost -ml-3">
        ← Назад
      </button>

      <div>
        <h1 className="text-xl font-semibold leading-tight mb-1">
          {v.title ?? "—"}
        </h1>
        <div className="text-tg-hint">
          {v.company_name ?? "—"}
          {v.area_name && ` · ${v.area_name}`}
        </div>
        <div className="text-base mt-1">
          {formatSalary(v.salary_from, v.salary_to, v.salary_currency)}
        </div>
        <div className="text-xs text-tg-hint mt-1">
          Опубликовано {formatDate(v.published_at)}
        </div>
      </div>

      {/* Score block */}
      <Card>
        {cachedScore !== null ? (
          <>
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">Оценка соответствия</span>
              <Badge tone={scoreTone(cachedScore)}>{cachedScore}/100</Badge>
            </div>
            {feedItem?.reaction?.score_reason && (
              <p className="text-sm text-tg-text mb-2">{feedItem.reaction.score_reason}</p>
            )}
            {feedItem?.reaction?.red_flags?.length ? (
              <div>
                <div className="text-xs text-tg-hint mb-1">Красные флаги:</div>
                <ul className="text-sm space-y-1">
                  {feedItem.reaction.red_flags.map((f, i) => (
                    <li key={i} className="text-tg-destructive">• {f}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <Button
              variant="ghost"
              loading={score.isPending}
              onClick={() => score.mutate()}
              className="mt-2 text-sm"
            >
              Пересчитать оценку
            </Button>
          </>
        ) : (
          <>
            <div className="font-medium mb-2">Оценка ещё не сделана</div>
            <Button loading={score.isPending} onClick={() => score.mutate()}>
              Оценить через ИИ
            </Button>
          </>
        )}
        {score.isError && (
          <div className="text-tg-destructive text-sm mt-2">
            {toApiError(score.error).detail}
          </div>
        )}
      </Card>

      {/* Reactions */}
      <div className="grid grid-cols-3 gap-2">
        <Button
          variant={feedItem?.reaction?.reaction === "like" ? "primary" : "secondary"}
          onClick={() => react.mutate("like")}
        >
          👍
        </Button>
        <Button
          variant={feedItem?.reaction?.reaction === "save" ? "primary" : "secondary"}
          onClick={() => react.mutate("save")}
        >
          ⭐
        </Button>
        <Button
          variant={feedItem?.reaction?.reaction === "skip" ? "primary" : "secondary"}
          onClick={() => react.mutate("skip")}
        >
          ✕
        </Button>
      </div>

      {/* Description */}
      {v.description && (
        <Card>
          <div className="text-sm font-medium mb-2">Описание</div>
          <div
            className="text-sm prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: v.description }}
          />
        </Card>
      )}

      {v.key_skills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {v.key_skills.map((s) => (
            <Badge key={s}>{s}</Badge>
          ))}
        </div>
      )}

      {/* Letter + Apply CTA */}
      <div className="grid grid-cols-2 gap-2 pt-2">
        <Button variant="secondary" onClick={() => nav(`/vacancies/${vacancyId}/letter`)}>
          ✉ Написать письмо
        </Button>
        <Button
          loading={apply.isPending}
          onClick={() => apply.mutate()}
          disabled={!!applyExistingId}
        >
          {applyExistingId ? "✓ Уже отклик есть" : "Я откликнулся"}
        </Button>
      </div>
      {apply.isError && !applyExistingId && (
        <div className="text-tg-destructive text-sm">
          {toApiError(apply.error).detail}
        </div>
      )}
      {applyExistingId && (
        <Button
          variant="ghost"
          className="w-full"
          onClick={() => nav(`/tracker?application=${applyExistingId}`)}
        >
          Открыть отклик в трекере →
        </Button>
      )}

      {v.url && (
        <a
          href={v.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-center text-tg-link text-sm py-3"
        >
          Открыть на источнике →
        </a>
      )}
    </div>
  );
}
