import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, Card, CenterLoader, PageError } from "@/components/ui";
import type { ProfileGrade } from "@/api/types";

const GRADES: ProfileGrade[] = ["junior", "middle", "senior", "lead"];

export function ProfilePage() {
  const { user } = useAuth();
  const profileId = user?.active_profile_id;
  const qc = useQueryClient();

  const profile = useQuery({
    queryKey: ["profile", profileId],
    queryFn: async () => {
      const list = await profilesApi.list();
      return list.find((p) => p.id === profileId) ?? null;
    },
    enabled: profileId !== null && profileId !== undefined,
  });

  const resume = useQuery({
    queryKey: ["resume", profileId],
    queryFn: () => profilesApi.getResume(profileId!),
    enabled: profileId !== null && profileId !== undefined,
  });

  const [stack, setStack] = useState("");
  const [grade, setGrade] = useState<ProfileGrade>("middle");
  const [salaryFrom, setSalaryFrom] = useState("");
  const [resumeText, setResumeText] = useState("");

  // Сихронизируем локальный стейт когда профиль загрузится
  useEffect(() => {
    if (profile.data) {
      setStack(profile.data.stack.join(", "));
      setGrade(profile.data.grade ?? "middle");
      setSalaryFrom(profile.data.salary_from?.toString() ?? "");
    }
  }, [profile.data]);

  useEffect(() => {
    if (resume.data) {
      setResumeText(resume.data.resume_text ?? "");
    }
  }, [resume.data]);

  const savePatch = useMutation({
    mutationFn: () =>
      profilesApi.update(profileId!, {
        stack: stack.split(",").map((s) => s.trim()).filter(Boolean),
        grade,
        salary_from: salaryFrom ? Number(salaryFrom) : null,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["profile", profileId] }),
  });

  const saveResume = useMutation({
    mutationFn: () => profilesApi.setResume(profileId!, resumeText),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resume", profileId] });
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
    },
  });

  if (profile.isLoading) return <CenterLoader />;
  if (profile.isError) return <PageError message={toApiError(profile.error).detail} />;
  if (!profile.data) return <PageError message="Профиль не найден" />;

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-semibold">{profile.data.name}</h1>
      <div className="text-tg-hint text-sm -mt-3">
        @{user?.username ?? "—"} · {user?.first_name ?? ""}
      </div>

      <Card className="space-y-3">
        <div>
          <label className="block text-sm mb-1">Стек</label>
          <input
            className="input"
            value={stack}
            onChange={(e) => setStack(e.target.value)}
            placeholder="python, fastapi, ..."
          />
        </div>
        <div>
          <label className="block text-sm mb-1">Грейд</label>
          <div className="flex gap-2">
            {GRADES.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGrade(g)}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  grade === g
                    ? "bg-tg-btn text-tg-btn-text"
                    : "bg-tg-bg border border-tg-secondary-bg"
                }`}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-sm mb-1">Желаемая ЗП от</label>
          <input
            className="input"
            type="number"
            inputMode="numeric"
            value={salaryFrom}
            onChange={(e) => setSalaryFrom(e.target.value)}
          />
        </div>
        <Button
          className="w-full"
          loading={savePatch.isPending}
          onClick={() => savePatch.mutate()}
        >
          Сохранить
        </Button>
        {savePatch.isError && (
          <div className="text-tg-destructive text-sm">
            {toApiError(savePatch.error).detail}
          </div>
        )}
      </Card>

      <Card className="space-y-3">
        <div className="font-medium">Резюме</div>
        <div className="text-xs text-tg-hint">
          Вставьте текст резюме — он будет использоваться для генерации
          сопроводительных и более точной оценки. Шифруется на сервере.
        </div>
        <textarea
          className="input min-h-[200px] text-sm"
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          placeholder="Senior Python разработчик. 5 лет опыта..."
          maxLength={100000}
        />
        <div className="text-xs text-tg-hint">{resumeText.length} символов</div>
        <Button
          variant="secondary"
          className="w-full"
          loading={saveResume.isPending}
          disabled={!resumeText.trim()}
          onClick={() => saveResume.mutate()}
        >
          Сохранить резюме
        </Button>
      </Card>
    </div>
  );
}
