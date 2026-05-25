import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { lettersApi, vacanciesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, Card, CenterLoader, PageError } from "@/components/ui";
import { haptic } from "@/lib/telegram";

export function LetterPage() {
  const { id: idStr } = useParams<{ id: string }>();
  const vacancyId = Number(idStr);
  const profileId = useAuth((s) => s.user?.active_profile_id);
  const nav = useNavigate();

  const [extra, setExtra] = useState("");
  const [editedText, setEditedText] = useState<string | null>(null);

  const vacancy = useQuery({
    queryKey: ["vacancy", vacancyId],
    queryFn: () => vacanciesApi.get(vacancyId),
    enabled: Number.isFinite(vacancyId),
  });

  const generate = useMutation({
    mutationFn: () =>
      lettersApi.generate(vacancyId, profileId!, extra.trim() || undefined),
    onSuccess: (res) => {
      setEditedText(res.letter.text);
      haptic("medium");
    },
  });

  const copyToClipboard = async () => {
    if (!editedText) return;
    try {
      await navigator.clipboard.writeText(editedText);
      haptic("light");
    } catch {
      // fallback в Telegram WebView не критично
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
      ) : (
        <>
          <Card>
            <div className="text-sm font-medium mb-2">Письмо</div>
            <textarea
              className="input min-h-[300px] text-sm leading-relaxed"
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
            />
            <div className="text-xs text-tg-hint mt-1">
              {editedText.length} символов · можете отредактировать
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
              }}
            >
              Сгенерировать снова
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
