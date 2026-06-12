import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lettersApi, letterTemplatesApi, vacanciesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, Card, CenterLoader, PageError } from "@/components/ui";
import { ExpandableTextarea } from "@/components/ExpandableTextarea";
import { toast } from "@/lib/toast";

export function LetterPage() {
  const { id: idStr } = useParams<{ id: string }>();
  const vacancyId = Number(idStr);
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const nav = useNavigate();
  const qc = useQueryClient();

  const [extra, setExtra] = useState("");
  const [editedText, setEditedText] = useState<string | null>(null);
  const [tplTitle, setTplTitle] = useState("");
  const [savingTpl, setSavingTpl] = useState(false);

  const vacancy = useQuery({
    queryKey: ["vacancy", vacancyId],
    queryFn: () => vacanciesApi.get(vacancyId),
    enabled: Number.isFinite(vacancyId),
  });

  const templates = useQuery({
    queryKey: ["letter-templates", profileId],
    queryFn: () => letterTemplatesApi.list(profileId!),
    enabled: !!profileId,
  });

  // Подставляем {company}/{position} в тело шаблона из текущей вакансии.
  const fillTemplate = (body: string): string =>
    body
      .replaceAll("{company}", vacancy.data?.company_name ?? "")
      .replaceAll("{position}", vacancy.data?.title ?? "");

  const saveTemplate = useMutation({
    mutationFn: () =>
      letterTemplatesApi.create(profileId!, {
        title: tplTitle.trim(),
        body: editedText ?? "",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["letter-templates", profileId] });
      toast.success("Шаблон сохранён");
      setSavingTpl(false);
      setTplTitle("");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const deleteTemplate = useMutation({
    mutationFn: (id: number) => letterTemplatesApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["letter-templates", profileId] });
      toast.success("Шаблон удалён");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const generate = useMutation({
    mutationFn: () =>
      lettersApi.generate(vacancyId, profileId!, extra.trim() || undefined),
    onSuccess: (res) => {
      setEditedText(res.letter.text);
      toast.success("Письмо готово");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const copyToClipboard = async () => {
    if (!editedText) return;
    try {
      await navigator.clipboard.writeText(editedText);
      toast.success("Скопировано");
    } catch {
      // fallback в Telegram WebView не критично
      toast.error("Не удалось скопировать");
    }
  };

  if (vacancy.isLoading) return <CenterLoader />;
  if (vacancy.isError) return <PageError message={toApiError(vacancy.error).detail} />;

  return (
    <div className="p-4 space-y-4">
      <button onClick={() => nav(-1)} className="btn-ghost -ml-3">
        ← Назад
      </button>

      <h1 className="text-xl font-semibold">Сопроводительное</h1>
      <div className="text-tg-hint text-sm -mt-3">
        {vacancy.data?.title} · {vacancy.data?.company_name}
      </div>

      {!editedText ? (
        <>
          <Card className="space-y-3">
            <div className="text-sm">
              Опционально — что подчеркнуть или упомянуть:
            </div>
            <textarea
              className="input min-h-[80px]"
              placeholder="Например, мой опыт с Kubernetes, готовность к гибриду..."
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              maxLength={2000}
            />
            <div className="text-xs text-tg-hint">
              {extra.length} / 2000
            </div>
            <Button
              className="w-full"
              loading={generate.isPending}
              onClick={() => generate.mutate()}
            >
              Сгенерировать
            </Button>
            {generate.isError && (
              <div className="text-tg-destructive text-sm">
                {toApiError(generate.error).detail}
              </div>
            )}
          </Card>

          {templates.data && templates.data.length > 0 && (
            <Card className="space-y-2">
              <div className="text-sm font-medium">Мои шаблоны</div>
              <div className="text-xs text-tg-hint -mt-1">
                Плейсхолдеры {"{company}"} и {"{position}"} подставятся автоматически.
              </div>
              {templates.data.map((t) => (
                <div key={t.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditedText(fillTemplate(t.body))}
                    className="flex-1 text-left text-sm rounded-lg bg-tg-secondary-bg px-3 py-2 truncate"
                  >
                    {t.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteTemplate.mutate(t.id)}
                    disabled={deleteTemplate.isPending}
                    className="text-tg-hint hover:text-tg-destructive px-1 disabled:opacity-50"
                    aria-label="Удалить шаблон"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </Card>
          )}
        </>
      ) : (
        <>
          <Card>
            <div className="text-sm font-medium mb-2">Письмо</div>
            <ExpandableTextarea
              value={editedText}
              onChange={setEditedText}
              minHeightClass="min-h-[300px]"
              title="Сопроводительное"
            />
            <div className="text-xs text-tg-hint mt-1">
              {editedText.length} символов · ⛶ — редактировать на весь экран
            </div>
          </Card>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={copyToClipboard}>
              📋 Копировать
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setEditedText(null);
                generate.reset();
                setSavingTpl(false);
              }}
            >
              Сгенерировать снова
            </Button>
          </div>

          {!savingTpl ? (
            <Button variant="ghost" className="w-full" onClick={() => setSavingTpl(true)}>
              💾 Сохранить как шаблон
            </Button>
          ) : (
            <Card className="space-y-2">
              <div className="text-sm font-medium">Новый шаблон</div>
              <div className="text-xs text-tg-hint -mt-1">
                Совет: замените название компании на {"{company}"}, должность — на{" "}
                {"{position}"}, чтобы переиспользовать письмо.
              </div>
              <input
                className="input"
                placeholder="Название шаблона"
                value={tplTitle}
                onChange={(e) => setTplTitle(e.target.value)}
                maxLength={120}
              />
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSavingTpl(false);
                    setTplTitle("");
                  }}
                >
                  Отмена
                </Button>
                <Button
                  loading={saveTemplate.isPending}
                  disabled={!tplTitle.trim()}
                  onClick={() => saveTemplate.mutate()}
                >
                  Сохранить
                </Button>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
