/**
 * Минимальный набор UI-примитивов поверх Tailwind. Без зависимостей.
 */

import { type ButtonHTMLAttributes, type ReactNode } from "react";

export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className="animate-spin text-tg-link"
      fill="none"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "destructive";
const VARIANT_CLASS: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  destructive:
    "bg-tg-destructive text-white rounded-lg py-2.5 px-4 font-medium hover:opacity-90 disabled:opacity-50",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

export function Button({
  variant = "primary",
  loading = false,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`${VARIANT_CLASS[variant]} inline-flex items-center justify-center gap-2 ${className}`}
    >
      {loading && <Spinner size={16} />}
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function PageError({ message }: { message: string }) {
  return (
    <div className="p-6 text-center">
      <div className="text-tg-destructive font-medium mb-2">Ошибка</div>
      <div className="text-tg-hint text-sm">{message}</div>
    </div>
  );
}

export function CenterLoader() {
  return (
    <div className="h-full flex items-center justify-center">
      <Spinner size={32} />
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-tg-secondary-bg ${className}`} />;
}

/** Карточка-заглушка для списков (Feed/Tracker) во время загрузки. */
export function SkeletonCard() {
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-16" />
      </div>
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}

export function SkeletonList({ count = 4 }: { count?: number }) {
  return (
    <div className="p-4 space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="p-6 text-center">
      <div className="text-base font-medium mb-1">{title}</div>
      {hint && <div className="text-tg-hint text-sm mb-4">{hint}</div>}
      {action}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const cls = {
    neutral: "bg-tg-secondary-bg text-tg-text",
    good: "bg-green-100 text-green-800",
    warn: "bg-yellow-100 text-yellow-800",
    bad: "bg-red-100 text-red-800",
  }[tone];
  return <span className={`inline-block px-2 py-0.5 rounded text-xs ${cls}`}>{children}</span>;
}
