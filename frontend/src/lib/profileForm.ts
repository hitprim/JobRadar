/**
 * Чистая логика формы профиля (состояние, конвертация в API-payload, валидация).
 * Отделена от компонента <ProfileForm/>, чтобы react-refresh не ругался на
 * смешанные экспорты и чтобы логику можно было тестировать без React.
 */

import type {
  Experience,
  ProfileCreateRequest,
  ProfileGrade,
  Schedule,
  WorkFormat,
  Profile,
} from "@/api/types";

/** Состояние формы. Списочные поля (stack/excludeKeywords) — строки через запятую. */
export interface ProfileFormValue {
  name: string;
  stack: string;
  grade: ProfileGrade;
  salaryFrom: string;
  workFormat: WorkFormat[];
  schedule: Schedule[];
  areaIds: number[];
  experience: Experience[];
  excludeKeywords: string;
}

export function emptyProfileForm(): ProfileFormValue {
  return {
    name: "",
    stack: "",
    grade: "middle",
    salaryFrom: "",
    workFormat: ["remote"],
    schedule: [],
    areaIds: [],
    experience: [],
    excludeKeywords: "",
  };
}

/** Профиль из API → состояние формы (для экрана редактирования). */
export function profileFormFromProfile(p: Profile): ProfileFormValue {
  return {
    name: p.name,
    stack: p.stack.join(", "),
    grade: p.grade ?? "middle",
    salaryFrom: p.salary_from?.toString() ?? "",
    workFormat: p.work_format,
    schedule: p.schedule,
    areaIds: p.area_ids,
    experience: p.experience,
    excludeKeywords: p.exclude_keywords.join(", "),
  };
}

const splitCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

/** Город важен только для офиса/гибрида. */
export function profileNeedsCity(v: ProfileFormValue): boolean {
  return v.workFormat.includes("office") || v.workFormat.includes("hybrid");
}

/** Состояние формы → payload для create/update. fallbackName — если имя пустое. */
export function profileFormToPayload(
  v: ProfileFormValue,
  fallbackName = "Мой профиль",
): ProfileCreateRequest {
  return {
    name: v.name.trim() || fallbackName,
    category: "it",
    grade: v.grade,
    stack: splitCsv(v.stack),
    salary_from: v.salaryFrom ? Number(v.salaryFrom) : null,
    work_format: v.workFormat,
    schedule: v.schedule,
    experience: v.experience,
    area_ids: profileNeedsCity(v) ? v.areaIds : [],
    exclude_keywords: splitCsv(v.excludeKeywords),
  };
}

/** Можно ли сохранять (общая валидация для обоих экранов). */
export function isProfileFormValid(v: ProfileFormValue): boolean {
  return v.workFormat.length > 0 && !(profileNeedsCity(v) && v.areaIds.length === 0);
}
