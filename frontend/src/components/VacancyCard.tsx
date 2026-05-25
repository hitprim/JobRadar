import { Link } from "react-router-dom";
import type { FeedItem } from "@/api/types";
import { Badge, Card } from "@/components/ui";
import { formatDate, formatSalary, scoreTone } from "@/lib/format";

export function VacancyCard({ item }: { item: FeedItem }) {
  const { vacancy, reaction } = item;
  const score = reaction?.score ?? null;
  return (
    <Link to={`/vacancies/${vacancy.id}`} className="block">
      <Card className="hover:opacity-90 transition-opacity">
        <div className="flex items-start justify-between gap-2 mb-1">
          <h3 className="font-medium text-base flex-1 leading-tight">
            {vacancy.title ?? "—"}
          </h3>
          {score !== null && (
            <Badge tone={scoreTone(score)}>{score}</Badge>
          )}
        </div>
        <div className="text-tg-hint text-sm">
          {vacancy.company_name ?? "—"}
          {vacancy.area_name && ` · ${vacancy.area_name}`}
        </div>
        <div className="text-sm mt-1.5">
          {formatSalary(vacancy.salary_from, vacancy.salary_to, vacancy.salary_currency)}
        </div>
        <div className="flex items-center justify-between mt-2 text-xs text-tg-hint">
          <span>{formatDate(vacancy.published_at)}</span>
          {reaction?.reaction === "save" && <span>⭐ В избранном</span>}
          {reaction?.reaction === "like" && <span>👍 Понравилась</span>}
          {reaction?.reaction === "skip" && <span>Пропущена</span>}
        </div>
      </Card>
    </Link>
  );
}
