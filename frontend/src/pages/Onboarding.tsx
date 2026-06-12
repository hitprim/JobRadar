/**
 * Создание профиля. Первый профиль → онбординг; при наличии активного —
 * создание дополнительного (мульти-профиль). После создания юзер попадает в Feed.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { profilesApi, sourcesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { Button, Card, PageError } from "@/components/ui";
import { toast } from "@/lib/toast";
import { ProfileForm } from "@/components/ProfileForm";
import {
  emptyProfileForm,
  isProfileFormValid,
  profileFormToPayload,
  type ProfileFormValue,
} from "@/lib/profileForm";
import { useAuth } from "@/store/auth";

export function OnboardingPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { user, updateUser } = useAuth();
  // Если активный профиль уже есть — это создание доп. профиля (мульти-профиль).
  const isAdditional = user?.active_profile_id != null;

  const [form, setForm] = useState<ProfileFormValue>(emptyProfileForm);
  const patch = (p: Partial<ProfileFormValue>) => setForm((prev) => ({ ...prev, ...p }));

  const create = useMutation({
    mutationFn: async () => {
      const profile = await profilesApi.create(profileFormToPayload(form));
      // Создаём hh-source автоматически — в v0.1 это единственный источник.
      await sourcesApi.create(profile.id, "hh");
      return profile;
    },
    onSuccess: (profile) => {
      updateUser({ active_profile_id: profile.id });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
      toast.success("Профиль создан");
      nav("/feed", { replace: true });
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  return (
    <div className="p-4 max-w-md mx-auto">
      <h1 className="text-2xl font-semibold mb-1">
        {isAdditional ? "Новый профиль" : "Добро пожаловать в JobRadar"}
      </h1>
      <p className="text-tg-hint text-sm mb-6">
        {isAdditional
          ? "Заполните параметры нового профиля. Он станет активным после создания."
          : "Расскажите о себе, чтобы мы могли искать релевантные вакансии. Изменить можно потом в Профиле."}
      </p>

      <Card>
        <ProfileForm value={form} onChange={patch} />
      </Card>

      {create.isError && <PageError message={toApiError(create.error).detail} />}

      <Button
        className="w-full mt-4"
        onClick={() => create.mutate()}
        loading={create.isPending}
        disabled={!form.stack.trim() || !isProfileFormValid(form)}
      >
        Создать профиль
      </Button>
    </div>
  );
}
