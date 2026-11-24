/**
 * Componenti di base dell'app. `Button` è un adattatore sopra il pulsante di shadcn/ui
 * (`@/components/ui/button`): stessa API usata in tutta l'app, stile e focus di shadcn.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Button as ShadcnButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT: Record<Variant, "default" | "outline" | "ghost" | "destructive"> = {
  primary: "default",
  secondary: "outline",
  ghost: "ghost",
  danger: "destructive",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "secondary", className, type = "button", ...props }: ButtonProps) {
  return (
    <ShadcnButton
      type={type}
      variant={VARIANT[variant]}
      className={cn(variant === "ghost" && "text-ink-muted", variant === "primary" && "font-semibold", className)}
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
        className={`h-full rounded-full bg-brand transition-[width] duration-300 ${pct == null ? "w-1/3 animate-pulse" : ""}`}
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
        className="rounded-md border border-line bg-ground px-2.5 py-1.5 text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none"
      />
    </label>
  );
}
