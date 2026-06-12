import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applicationsApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageError,
  SkeletonList,
} from "@/components/ui";
import { ExpandableTextarea } from "@/components/ExpandableTextarea";
import { toast } from "@/lib/toast";
import { APPLICATION_STATUS_RU, formatDateTime } from "@/lib/format";
import type { ApplicationListItem, ApplicationStatus } from "@/api/types";

const STATUS_ORDER: ApplicationStatus[] = ["sent", "hr", "tech", "final", "offer", "reject"];

const STATUS_TONE: Record<ApplicationStatus, "neutral" | "good" | "warn" | "bad"> = {
  sent: "neutral",
  hr: "neutral",
  tech: "warn",
  final: "warn",
  offer: "good",
  reject: "bad",
};

/** ISO → значение для <input type="datetime-local"> (локальное время, без TZ-суффикса). */
function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Значение datetime-local → ISO (или null, если пусто). */
function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function TrackerCard({
  app,
  profileId,
}: {
  app: ApplicationListItem;
  profileId: number;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState(app.notes ?? "");
  const [reminder, setReminder] = useState(isoToLocalInput(app.next_reminder_at));

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["applications", profileId] });
    void qc.invalidateQueries({ queryKey: ["funnel", profileId] });
  };

  const updateStatus = useMutation({
    mutationFn: (status: ApplicationStatus) => applicationsApi.patch(app.id, { status }),
    onSuccess: (_data, status) => {
      invalidate();
      toast.success(`Статус: ${APPLICATION_STATUS_RU[status]}`);
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const saveDetails = useMutation({
    mutationFn: () =>
      applicationsApi.patch(app.id, {
        notes: notes.trim(),
        next_reminder_at: localInputToIso(reminder),
      }),
    onSuccess: () => {
      invalidate();
      setEditing(false);
      toast.success("Сохранено");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const dirty =
    notes.trim() !== (app.notes ?? "").trim() ||
    localInputToIso(reminder) !== app.next_reminder_at;

  return (
    <Card>
      <div className="flex items-center justify-between mb-2">
        <Badge tone={STATUS_TONE[app.status]}>{APPLICATION_STATUS_RU[app.status]}</Badge>
        <span className="text-xs text-tg-hint">{formatDateTime(app.created_at)}</span>
      </div>

      <div className="mb-1 font-medium leading-snug">
        {app.vacancy_title ?? `Вакансия #${app.vacancy_id}`}
      </div>
      {app.company_name && (
        <div className="text-sm text-tg-hint mb-2">{app.company_name}</div>
      )}

      {app.next_reminder_at && !editing && (
        <div className="text-xs text-tg-link mb-2">
          ⏰ Напоминание: {formatDateTime(app.next_reminder_at)}
        </div>
      )}

      {!editing ? (
        <>
          {app.notes && (
            <div className="text-sm bg-tg-bg p-2 rounded mb-2 whitespace-pre-wrap">
              {app.notes}
            </div>
          )}
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-tg-link mb-2 hover:opacity-80"
          >
            ✎ {app.notes || app.next_reminder_at ? "Заметка и напоминание" : "Добавить заметку / напоминание"}
          </button>
        </>
      ) : (
        <div className="space-y-2 mb-3">
          <div>
            <label className="block text-xs text-tg-hint mb-1">Заметка</label>
            <ExpandableTextarea
              value={notes}
              onChange={setNotes}
              minHeightClass="min-h-[80px]"
              title="Заметка"
              placeholder="Контакт HR, договорённости, дедлайны..."
              maxLength={5000}
            />
          </div>
          <div>
            <label className="block text-xs text-tg-hint mb-1">Напомнить</label>
            <input
              type="datetime-local"
              className="input"
              value={reminder}
              onChange={(e) => setReminder(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button
              loading={saveDetails.isPending}
              disabled={!dirty}
              onClick={() => saveDetails.mutate()}
            >
              Сохранить
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setNotes(app.notes ?? "");
                setReminder(isoToLocalInput(app.next_reminder_at));
                setEditing(false);
              }}
            >
              Отмена
            </Button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1">
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            onClick={() => updateStatus.mutate(s)}
            disabled={app.status === s || updateStatus.isPending}
            className={`text-xs px-2 py-1 rounded transition-opacity ${
              app.status === s
                ? "bg-tg-btn text-tg-btn-text"
                : "bg-tg-bg text-tg-text border border-tg-secondary-bg hover:opacity-80"
            } disabled:cursor-not-allowed`}
          >
            {APPLICATION_STATUS_RU[s]}
          </button>
        ))}
      </div>
    </Card>
  );
}

export function TrackerPage() {
  const profileId = useAuth((s) => s.user?.active_profile_id);

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

  const exportCsv = useMutation({
    mutationFn: () => applicationsApi.exportCsv(profileId!),
    onSuccess: (blob) => {
      // Скачиваем blob через временную ссылку. В Telegram WebView может не
      // сработать — это known limitation, занесено в техдолг.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jobradar_tracker_${profileId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("CSV выгружен");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  if (!profileId) return null;
  if (apps.isLoading || funnel.isLoading) return <SkeletonList count={4} />;
  if (apps.isError) return <PageError message={toApiError(apps.error).detail} />;

  const list = apps.data ?? [];
  const f = funnel.data;

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Трекер</h1>
        {list.length > 0 && (
          <Button
            variant="secondary"
            loading={exportCsv.isPending}
            onClick={() => exportCsv.mutate()}
          >
            ⬇ CSV
          </Button>
        )}
      </div>

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
                  <span className="w-24 text-tg-hint">{APPLICATION_STATUS_RU[s]}</span>
                  <div className="flex-1 bg-tg-bg rounded h-2 overflow-hidden">
                    <div className="h-full bg-tg-link" style={{ width: `${pct}%` }} />
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
            <TrackerCard key={a.id} app={a} profileId={profileId} />
          ))}
        </div>
      )}
    </div>
  );
}
