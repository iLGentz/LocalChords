/** Componenti di base condivisi (sostituibili con shadcn/ui nella fase 8). */
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-ground hover:brightness-110 font-semibold",
  secondary: "border border-line bg-raised text-ink hover:border-ink-muted",
  ghost: "text-ink-muted hover:text-ink hover:bg-raised",
  danger: "border border-bad/50 text-bad hover:bg-bad/10",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${className}`}
      {...props}
    />
  );
}

interface ProgressBarProps {
  value: number | null;
  label: string;
}

/** Barra di avanzamento; `value` null = indeterminata. */
export function ProgressBar({ value, label }: ProgressBarProps) {
  const pct = value == null ? null : Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      {...(pct != null ? { "aria-valuenow": pct } : {})}
      className="h-1.5 w-full overflow-hidden rounded-full bg-raised"
    >
      <div
        className={`h-full rounded-full bg-accent transition-[width] duration-300 ${pct == null ? "w-1/3 animate-pulse" : ""}`}
        style={pct != null ? { width: `${pct}%` } : undefined}
      />
    </div>
  );
}

interface NoticeProps {
  tone: "error" | "warn" | "info";
  title?: string;
  children: ReactNode;
  action?: ReactNode;
}

const NOTICE_TONE: Record<NoticeProps["tone"], string> = {
  error: "border-bad/40 bg-bad/10",
  warn: "border-warn/40 bg-warn/10",
  info: "border-line bg-raised",
};

export function Notice({ tone, title, children, action }: NoticeProps) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex flex-wrap items-start justify-between gap-3 rounded-md border px-3 py-2.5 text-sm ${NOTICE_TONE[tone]}`}
    >
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        <div className="text-ink-muted">{children}</div>
      </div>
      {action}
    </div>
  );
}

interface FieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
}

export function TextField({ id, label, value, onChange, required, placeholder }: FieldProps) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-sm">
      <span className="text-ink-muted">
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </span>
      <input
        id={id}
        value={value}
        required={required}
        placeholder={placeholder}
        maxLength={500}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line bg-ground px-2.5 py-1.5 text-ink placeholder:text-ink-muted/60 focus:border-accent focus:outline-none"
      />
    </label>
  );
}
