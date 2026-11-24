type Tone = "ok" | "warn" | "bad" | "idle";

const DOT: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  idle: "bg-ink-muted animate-pulse",
};

interface StatusBadgeProps {
  label: string;
  value: string;
  tone: Tone;
  title?: string;
}

export function StatusBadge({ label, value, tone, title }: StatusBadgeProps) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1 text-xs"
      title={title}
    >
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT[tone]}`} />
      <span className="text-ink-muted">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </span>
  );
}
