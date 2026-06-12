import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { companyReviewsApi } from "@/api/endpoints";
import { toApiError } from "@/api/client";
import type { CompanyReview, CompanyReviewCreateRequest } from "@/api/types";
import { Badge, Button, Card, Spinner } from "@/components/ui";
import { toast } from "@/lib/toast";
import { formatDate } from "@/lib/format";
import {
  SIGNAL_GROUPS,
  respectTone,
  respectWord,
  reviewSignalLabels,
} from "@/lib/companyReview";

type Draft = Partial<Record<(typeof SIGNAL_GROUPS)[number]["key"], string>>;

function draftFromReview(review: CompanyReview | null): Draft {
  if (!review) return {};
  return {
    responded: review.responded,
    respect: review.respect,
    feedback: review.feedback,
    honesty: review.honesty,
    process: review.process,
  };
}

// Сколько отзывов показываем сразу (остальные — по кнопке «Показать ещё»).
const VISIBLE_REVIEWS = 3;

function ReviewItem({
  review,
  isMine,
  onReport,
  reporting,
}: {
  review: CompanyReview;
  isMine: boolean;
  onReport: (reviewId: number) => void;
  reporting: boolean;
}) {
  const labels = reviewSignalLabels(review);
  return (
    <div className="border-t border-tg-secondary-bg pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between mb-1.5">
        <Badge tone={respectTone(review.score)}>{review.score}/100</Badge>
        <span className="text-xs text-tg-hint">{formatDate(review.created_at)}</span>
      </div>
      <div className="flex flex-wrap gap-1 mb-1.5">
        {labels.map((l, i) => (
          <span
            key={i}
            className="text-xs px-1.5 py-0.5 rounded bg-tg-secondary-bg text-tg-text"
          >
            {l}
          </span>
        ))}
      </div>
      {review.text && (
        <p className="text-sm text-tg-text whitespace-pre-wrap">{review.text}</p>
      )}
      {!isMine && (
        <button
          type="button"
          disabled={reporting}
          onClick={() => onReport(review.id)}
          className="mt-1.5 text-xs text-tg-hint hover:text-tg-destructive disabled:opacity-50"
        >
          {reporting ? "Отправляем…" : "⚑ Пожаловаться"}
        </button>
      )}
    </div>
  );
}

export function CompanyReviewSection({
  vacancyId,
  profileId,
}: {
  vacancyId: number;
  profileId: number | null | undefined;
}) {
  const qc = useQueryClient();
  const view = useQuery({
    queryKey: ["company-review", vacancyId],
    queryFn: () => companyReviewsApi.get(vacancyId),
    enabled: Number.isFinite(vacancyId),
  });

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>({});
  const [text, setText] = useState("");
  const [showAll, setShowAll] = useState(false);

  const report = useMutation({
    mutationFn: (reviewId: number) => companyReviewsApi.report(reviewId),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["company-review", vacancyId] });
      void qc.invalidateQueries({ queryKey: ["feed", profileId] });
      toast.success(res.hidden ? "Отзыв скрыт по жалобам" : "Жалоба отправлена");
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  // Открываем форму, подставляя существующий отзыв (если он есть).
  const openForm = (myReview: CompanyReview | null) => {
    setDraft(draftFromReview(myReview));
    setText(myReview?.text ?? "");
    setOpen(true);
  };

  const submit = useMutation({
    mutationFn: () => {
      const body: CompanyReviewCreateRequest = {
        responded: draft.responded as CompanyReviewCreateRequest["responded"],
        respect: draft.respect as CompanyReviewCreateRequest["respect"],
        feedback: draft.feedback as CompanyReviewCreateRequest["feedback"],
        honesty: draft.honesty as CompanyReviewCreateRequest["honesty"],
        process: draft.process as CompanyReviewCreateRequest["process"],
        text: text.trim() ? text.trim() : null,
      };
      return companyReviewsApi.submit(vacancyId, body, profileId ?? undefined);
    },
    onSuccess: (data) => {
      qc.setQueryData(["company-review", vacancyId], data);
      void qc.invalidateQueries({ queryKey: ["feed", profileId] });
      toast.success("Спасибо за отзыв!");
      setOpen(false);
    },
    onError: (e) => toast.error(toApiError(e).detail),
  });

  if (view.isLoading) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-sm text-tg-hint">
          <Spinner size={16} /> Загружаем отзывы о компании…
        </div>
      </Card>
    );
  }
  if (view.isError || !view.data) return null;
  const v = view.data;

  // Компанию нельзя опознать (нет company_id/названия) — секцию не показываем.
  if (v.company_key === null) return null;

  const allPicked = SIGNAL_GROUPS.every((g) => draft[g.key]);

  return (
    <Card>
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium">Как компания относится к соискателям</span>
        {v.review_count > 0 && (
          <Badge tone={respectTone(v.respect_score)}>
            {respectWord(v.respect_score)}
            {v.respect_score !== null && ` · ${v.respect_score}`}
          </Badge>
        )}
      </div>

      {v.review_count === 0 ? (
        <p className="text-sm text-tg-hint mb-2">
          Пока нет отзывов. {v.can_review ? "Будьте первым." : ""}
        </p>
      ) : (
        <div className="text-xs text-tg-hint mb-3">
          На основе {v.review_count}{" "}
          {v.review_count === 1 ? "отзыва" : "отзывов"} от тех, кто откликался.
        </div>
      )}

      {v.reviews.length > 0 && (
        <div className="space-y-3 mb-3">
          {(showAll ? v.reviews : v.reviews.slice(0, VISIBLE_REVIEWS)).map((r) => (
            <ReviewItem
              key={r.id}
              review={r}
              isMine={v.my_review?.id === r.id}
              onReport={(id) => report.mutate(id)}
              reporting={report.isPending && report.variables === r.id}
            />
          ))}
          {!showAll && v.reviews.length > VISIBLE_REVIEWS && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="text-sm text-tg-link"
            >
              Показать ещё {v.reviews.length - VISIBLE_REVIEWS}
            </button>
          )}
        </div>
      )}

      {/* CTA / форма */}
      {v.can_review ? (
        !open ? (
          <Button variant="secondary" onClick={() => openForm(v.my_review)}>
            {v.my_review ? "Изменить мой отзыв" : "Оставить отзыв"}
          </Button>
        ) : (
          <div className="space-y-4 pt-1">
            {SIGNAL_GROUPS.map((g) => (
              <div key={g.key}>
                <div className="text-sm font-medium mb-1.5">{g.question}</div>
                <div className="grid grid-cols-3 gap-1.5">
                  {g.options.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() =>
                        setDraft((d) => ({ ...d, [g.key]: o.value }))
                      }
                      className={`text-xs rounded-lg px-2 py-2 leading-tight border transition-colors ${
                        draft[g.key] === o.value
                          ? "bg-tg-link text-white border-tg-link"
                          : "bg-tg-secondary-bg text-tg-text border-transparent"
                      }`}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            <div>
              <div className="text-sm font-medium mb-1.5">
                Комментарий <span className="text-tg-hint">(необязательно)</span>
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="Как прошло общение? Пишите честно."
                className="w-full rounded-lg bg-tg-secondary-bg p-2.5 text-sm resize-none outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Отмена
              </Button>
              <Button
                loading={submit.isPending}
                disabled={!allPicked}
                onClick={() => submit.mutate()}
              >
                Отправить
              </Button>
            </div>
            {!allPicked && (
              <div className="text-xs text-tg-hint">
                Ответьте на все 5 вопросов, чтобы отправить отзыв.
              </div>
            )}
          </div>
        )
      ) : (
        <div className="text-xs text-tg-hint">
          Оставить отзыв можно после отклика на вакансию этой компании.
        </div>
      )}
    </Card>
  );
}
