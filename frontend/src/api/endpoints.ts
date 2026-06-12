/**
 * Тонкие обёртки над axios для каждого endpoint'а.
 * Сюда не добавляем кэширование/мутации — это уровень TanStack Query (см. hooks/).
 */

import { apiClient } from "./client";
import type {
  Application,
  ApplicationListItem,
  ApplicationStatus,
  ApplicationStatusHistory,
  CompanyReviewCreateRequest,
  CompanyReviewReportResponse,
  CompanyReviewView,
  FeedItem,
  FunnelStats,
  Letter,
  LetterGenerateResponse,
  LetterTemplate,
  LetterTemplateCreateRequest,
  LetterTemplatePatchRequest,
  RefreshAccepted,
  Profile,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ResumeResponse,
  ScoreResponse,
  Source,
  TelegramAuthResponse,
  Vacancy,
  VacancyReaction,
} from "./types";

// ---- Auth ----

export const authApi = {
  telegram: (init_data: string) =>
    apiClient
      .post<TelegramAuthResponse>("/auth/telegram", { init_data })
      .then((r) => r.data),
  dev: () =>
    apiClient.post<TelegramAuthResponse>("/auth/dev").then((r) => r.data),
};

// ---- Profiles ----

export const profilesApi = {
  list: () => apiClient.get<Profile[]>("/profiles").then((r) => r.data),
  create: (body: ProfileCreateRequest) =>
    apiClient.post<Profile>("/profiles", body).then((r) => r.data),
  update: (id: number, body: ProfileUpdateRequest) =>
    apiClient.patch<Profile>(`/profiles/${id}`, body).then((r) => r.data),
  remove: (id: number) =>
    apiClient.delete<void>(`/profiles/${id}`).then((r) => r.data),
  activate: (id: number) =>
    apiClient.post<void>(`/profiles/${id}/activate`).then((r) => r.data),
  getResume: (id: number) =>
    apiClient.get<ResumeResponse>(`/profiles/${id}/resume`).then((r) => r.data),
  setResume: (id: number, resume_text: string) =>
    apiClient
      .put<void>(`/profiles/${id}/resume`, { resume_text })
      .then((r) => r.data),
};

// ---- Sources ----

export const sourcesApi = {
  list: (profileId: number) =>
    apiClient.get<Source[]>(`/profiles/${profileId}/sources`).then((r) => r.data),
  create: (profileId: number, type: "hh" = "hh") =>
    apiClient
      .post<Source>(`/profiles/${profileId}/sources`, { type })
      .then((r) => r.data),
  remove: (sourceId: number) =>
    apiClient.delete<void>(`/sources/${sourceId}`).then((r) => r.data),
  refresh: (sourceId: number) =>
    apiClient
      .post<RefreshAccepted>(`/sources/${sourceId}/refresh`)
      .then((r) => r.data),
};

// ---- Vacancies / Feed ----

export type FeedFilter = "like" | "save" | "skip" | "all";

export const vacanciesApi = {
  feed: (
    profileId: number,
    params?: { reaction?: FeedFilter; limit?: number; offset?: number },
  ) =>
    apiClient
      .get<FeedItem[]>(`/profiles/${profileId}/feed`, {
        params: {
          limit: params?.limit ?? 50,
          offset: params?.offset ?? 0,
          // undefined → axios не добавит параметр (лента «Все» по умолчанию)
          reaction: params?.reaction,
        },
      })
      .then((r) => r.data),
  get: (id: number) => apiClient.get<Vacancy>(`/vacancies/${id}`).then((r) => r.data),
  react: (vacancyId: number, profileId: number, reaction: "like" | "skip" | "save") =>
    apiClient
      .post<VacancyReaction>(
        `/vacancies/${vacancyId}/reaction`,
        { reaction },
        { params: { profile_id: profileId } },
      )
      .then((r) => r.data),
  score: (vacancyId: number, profileId: number, force = false) =>
    apiClient
      .post<ScoreResponse>(`/vacancies/${vacancyId}/score`, undefined, {
        params: { profile_id: profileId, force },
      })
      .then((r) => r.data),
};

// ---- Company reviews (отзывы о компаниях) ----

export const companyReviewsApi = {
  get: (vacancyId: number) =>
    apiClient
      .get<CompanyReviewView>(`/vacancies/${vacancyId}/company-review`)
      .then((r) => r.data),
  submit: (
    vacancyId: number,
    body: CompanyReviewCreateRequest,
    profileId?: number,
  ) =>
    apiClient
      .post<CompanyReviewView>(`/vacancies/${vacancyId}/company-review`, body, {
        params: profileId !== undefined ? { profile_id: profileId } : undefined,
      })
      .then((r) => r.data),
  report: (reviewId: number) =>
    apiClient
      .post<CompanyReviewReportResponse>(`/company-reviews/${reviewId}/report`)
      .then((r) => r.data),
};

// ---- Letter templates (сохранённые шаблоны) ----

export const letterTemplatesApi = {
  list: (profileId: number) =>
    apiClient
      .get<LetterTemplate[]>(`/profiles/${profileId}/letter-templates`)
      .then((r) => r.data),
  create: (profileId: number, body: LetterTemplateCreateRequest) =>
    apiClient
      .post<LetterTemplate>(`/profiles/${profileId}/letter-templates`, body)
      .then((r) => r.data),
  update: (templateId: number, body: LetterTemplatePatchRequest) =>
    apiClient
      .patch<LetterTemplate>(`/letter-templates/${templateId}`, body)
      .then((r) => r.data),
  remove: (templateId: number) =>
    apiClient.delete<void>(`/letter-templates/${templateId}`).then((r) => r.data),
};

// ---- Letters ----

export const lettersApi = {
  generate: (vacancyId: number, profileId: number, extra_instructions?: string) =>
    apiClient
      .post<LetterGenerateResponse>(
        `/vacancies/${vacancyId}/letter`,
        { extra_instructions: extra_instructions ?? null },
        { params: { profile_id: profileId } },
      )
      .then((r) => r.data),
  get: (id: number) => apiClient.get<Letter>(`/letters/${id}`).then((r) => r.data),
  patch: (id: number, body: { text?: string; used_in_application?: boolean }) =>
    apiClient.patch<Letter>(`/letters/${id}`, body).then((r) => r.data),
  list: (profileId: number) =>
    apiClient
      .get<Letter[]>(`/profiles/${profileId}/letters`)
      .then((r) => r.data),
};

// ---- Applications (Tracker) ----

export const applicationsApi = {
  list: (profileId: number) =>
    apiClient
      .get<ApplicationListItem[]>(`/profiles/${profileId}/applications`)
      .then((r) => r.data),
  create: (
    profileId: number,
    body: { vacancy_id: number; cover_letter?: string; notes?: string },
  ) =>
    apiClient
      .post<Application>("/applications", body, { params: { profile_id: profileId } })
      .then((r) => r.data),
  get: (id: number) =>
    apiClient.get<Application>(`/applications/${id}`).then((r) => r.data),
  patch: (
    id: number,
    body: {
      status?: ApplicationStatus;
      notes?: string;
      cover_letter?: string;
      next_reminder_at?: string | null;
    },
  ) =>
    apiClient.patch<Application>(`/applications/${id}`, body).then((r) => r.data),
  history: (id: number) =>
    apiClient
      .get<ApplicationStatusHistory[]>(`/applications/${id}/history`)
      .then((r) => r.data),
  funnel: (profileId: number) =>
    apiClient.get<FunnelStats>(`/profiles/${profileId}/funnel`).then((r) => r.data),
  exportCsv: (profileId: number) =>
    apiClient
      .get(`/profiles/${profileId}/applications/export`, { responseType: "blob" })
      .then((r) => r.data as Blob),
};
