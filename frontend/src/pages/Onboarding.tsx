/**
 * Создание первого профиля. После создания юзер автоматически попадает в Feed.
 *
 * В v0.1 — один профиль на юзера, поэтому Onboarding показывается только
 * пока нет ни одного активного профиля.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { profilesApi, sourcesApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import { Button, Card, PageError } from "@/components/ui";
import { useAuth } from "@/store/auth";
import type { ProfileGrade } from "@/api/types";

const GRADES: { value: ProfileGrade; label: string }[] = [
  { value: "junior", label: "Junior" },
  { value: "middle", label: "Middle" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
];

export function OnboardingPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { updateUser } = useAuth();

  const [name, setName] = useState("");
  const [stack, setStack] = useState("");
  const [grade, setGrade] = useState<ProfileGrade>("middle");
  const [salaryFrom, setSalaryFrom] = useState("");
  const [remote, setRemote] = useState(true);

  const create = useMutation({
    mutationFn: async () => {
      const profile = await profilesApi.create({
        name: name.trim() || "Мой профиль",
        category: "it",
        grade,
        stack: stack.split(",").map((s) => s.trim()).filter(Boolean),
        salary_from: salaryFrom ? Number(salaryFrom) : null,
        work_format: remote ? ["remote", "hybrid"] : ["office", "hybrid"],
      });
      // Создаём hh-source автоматически — в v0.1 это единственный
      await sourcesApi.create(profile.id, "hh");
      return profile;
    },
    onSuccess: (profile) => {
      updateUser({ active_profile_id: profile.id });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
      nav("/feed", { replace: true });
    },
  });

  return (
    <div className="p-4 max-w-md mx-auto">
      <h1 className="text-2xl font-semibold mb-1">Добро пожаловать в JobRadar</h1>
      <p className="text-tg-hint text-sm mb-6">
        Расскажите о себе, чтобы мы могли искать релевантные вакансии. Изменить
        можно потом в Профиле.
      </p>

      <Card className="space-y-4">
        <div>
          <label className="block text-sm mb-1">Название профиля</label>
          <input
            className="input"
            placeholder="Например, Backend"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
          />
        </div>

        <div>
          <label className="block text-sm mb-1">Стек (через запятую)</label>
          <input
            className="input"
            placeholder="python, fastapi, postgresql"
            value={stack}
            onChange={(e) => setStack(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm mb-1">Грейд</label>
          <div className="flex gap-2">
            {GRADES.map((g) => (
              <button
                key={g.value}
                type="button"
                onClick={() => setGrade(g.value)}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  grade === g.value
                    ? "bg-tg-btn text-tg-btn-text"
                    : "bg-tg-bg border border-tg-secondary-bg text-tg-text"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm mb-1">Желаемая ЗП от, ₽</label>
          <input
            className="input"
            type="number"
            inputMode="numeric"
            placeholder="200000"
            value={salaryFrom}
            onChange={(e) => setSalaryFrom(e.target.value)}
          />
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={remote}
            onChange={(e) => setRemote(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-sm">Готов(а) к удалёнке</span>
        </label>
      </Card>

      {create.isError && (
        <PageError message={toApiError(create.error).detail} />
      )}

      <Button
        className="w-full mt-4"
        onClick={() => create.mutate()}
        loading={create.isPending}
        disabled={!stack.trim()}
      >
        Создать профиль
      </Button>
    </div>
  );
}
