import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { useAuth } from "@/store/auth";
import { Button, Card, CenterLoader, PageError } from "@/components/ui";
import { ProfileSwitcher } from "@/components/ProfileSwitcher";
import { ExpandableTextarea } from "@/components/ExpandableTextarea";
import { toast } from "@/lib/toast";
import { ProfileForm } from "@/components/ProfileForm";
import {
  emptyProfileForm,
  isProfileFormValid,
  profileFormFromProfile,
  profileFormToPayload,
  type ProfileFormValue,
} from "@/lib/profileForm";

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

  const [form, setForm] = useState<ProfileFormValue>(emptyProfileForm);
  const patch = (p: Partial<ProfileFormValue>) => setForm((prev) => ({ ...prev, ...p }));
  const [resumeText, setResumeText] = useState("");

  // Синхронизируем локальный стейт когда профиль загрузится.
  useEffect(() => {
    if (profile.data) setForm(profileFormFromProfile(profile.data));
  }, [profile.data]);

  useEffect(() => {
    if (resume.data) setResumeText(resume.data.resume_text ?? "");
  }, [resume.data]);

  const savePatch = useMutation({
    mutationFn: () =>
      profilesApi.update(profileId!, profileFormToPayload(form, profile.data!.name)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      toast.success("Сохранено");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  const saveResume = useMutation({
    mutationFn: () => profilesApi.setResume(profileId!, resumeText),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resume", profileId] });
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      toast.success("Резюме сохранено");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  if (profile.isLoading) return <CenterLoader />;
  if (profile.isError) return <PageError message={toApiError(profile.error).detail} />;
  if (!profile.data) return <PageError message="Профиль не найден" />;

  return (
    <div className="p-4 space-y-4">
      <div className="text-tg-hint text-sm">
        @{user?.username ?? "—"} · {user?.first_name ?? ""}
      </div>

      <ProfileSwitcher />

      <Card>
        <ProfileForm value={form} onChange={patch} />
        <Button
          className="w-full mt-4"
          loading={savePatch.isPending}
          disabled={!isProfileFormValid(form)}
          onClick={() => savePatch.mutate()}
        >
          Сохранить
        </Button>
      </Card>

      <Card className="space-y-3">
        <div className="font-medium">Резюме</div>
        <div className="text-xs text-tg-hint">
          Вставьте текст резюме — он будет использоваться для генерации
          сопроводительных и более точной оценки. Шифруется на сервере.
        </div>
        <ExpandableTextarea
          value={resumeText}
          onChange={setResumeText}
          minHeightClass="min-h-[200px]"
          title="Резюме"
          placeholder="Senior Python разработчик. 5 лет опыта..."
          maxLength={100000}
        />
        <div className="text-xs text-tg-hint">
          {resumeText.length} символов · ⛶ — редактировать на весь экран
        </div>
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
