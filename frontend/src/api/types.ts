/**
 * Типы DTO, синхронные с backend src/api/schemas.py.
 * Меняем здесь и в backend параллельно.
 */

export type ProfileCategory = "it" | "finance" | "sales" | "medical" | "service" | "production" | "other";
export type ProfileGrade = "junior" | "middle" | "senior" | "lead";
export type WorkFormat = "remote" | "hybrid" | "office";
export type Schedule = "fullDay" | "shift" | "flexible" | "part";
export type ApplicationStatus = "sent" | "hr" | "tech" | "final" | "offer" | "reject";

export interface UserPublic {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  active_profile_id: number | null;
  credits: number;
}

export interface TelegramAuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
  is_new_user: boolean;
}

export interface Profile {
  id: number;
  user_id: number;
  name: string;
  category: ProfileCategory;
  stack: string[];
  grade: ProfileGrade | null;
  salary_from: number | null;
  salary_to: number | null;
  salary_currency: string;
  work_format: WorkFormat[];
  schedule: Schedule[];
  area_ids: number[];
  exclude_keywords: string[];
  has_resume: boolean;
  category_data: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileCreateRequest {
  name: string;
  category?: ProfileCategory;
  stack?: string[];
  grade?: ProfileGrade | null;
  salary_from?: number | null;
  salary_to?: number | null;
  salary_currency?: string;
  work_format?: WorkFormat[];
  schedule?: Schedule[];
  area_ids?: number[];
  exclude_keywords?: string[];
}

export type ProfileUpdateRequest = Partial<ProfileCreateRequest>;

export interface Vacancy {
  id: number;
  external_id: string;
  source_type: string;
  title: string | null;
  company_name: string | null;
  company_id: string | null;
  salary_from: number | null;
  salary_to: number | null;
  salary_currency: string | null;
  url: string | null;
  area_name: string | null;
  schedule: string | null;
  experience: string | null;
  description: string | null;
  key_skills: string[];
  published_at: string | null;
  parsed_at: string;
}

export interface VacancyReaction {
  reaction: "like" | "skip" | "save" | null;
  score: number | null;
  score_reason: string | null;
  red_flags: string[];
  scored_at: string | null;
}

export interface FeedItem {
  vacancy: Vacancy;
  reaction: VacancyReaction | null;
}

export interface Source {
  id: number;
  profile_id: number;
  type: string;
  search_params: Record<string, unknown> | null;
  is_active: boolean;
  last_parsed_at: string | null;
  last_status: string | null;
  last_error: string | null;
  vacancies_today: number;
}

export interface ParseResult {
  source_id: number;
  fetched: number;
  inserted: number;
  updated: number;
  status: string;
  error: string | null;
}

export interface ScoreResponse {
  score: number;
  reason: string;
  red_flags: string[];
  green_flags: string[];
  from_cache: boolean;
}

export interface Letter {
  id: number;
  profile_id: number;
  vacancy_id: number;
  text: string | null;
  prompt_used: string | null;
  used_in_application: boolean;
  created_at: string;
}

export interface LetterGenerateResponse {
  letter: Letter;
  draft_notes: string[];
}

export interface Application {
  id: number;
  profile_id: number;
  vacancy_id: number;
  status: ApplicationStatus;
  cover_letter: string | null;
  notes: string | null;
  next_reminder_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationStatusHistory {
  id: number;
  application_id: number;
  status: ApplicationStatus;
  changed_at: string;
}

export interface FunnelStats {
  total: number;
  counts: Record<ApplicationStatus, number>;
  conversion_rates: Record<ApplicationStatus, number>;
}

export interface ResumeResponse {
  resume_text: string | null;
}
