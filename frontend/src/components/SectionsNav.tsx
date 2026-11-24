import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import type { SectionInfo } from "@/lib/api";
import { formatDuration } from "@/lib/format";

interface SectionsNavProps {
  sections: SectionInfo[];
  time: number;
  onSeek: (t: number) => void;
  onLoop: (a: number, b: number) => void;
}

/** Sezioni del brano nella colonna sinistra (portal nel segnaposto della barra laterale). */
export function SectionsNav({ sections, time, onSeek, onLoop }: SectionsNavProps) {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  useEffect(() => setTarget(document.getElementById("sidebar-sections")), []);
  if (!target || sections.length === 0) return null;

  return createPortal(
    <nav aria-label="Sezioni del brano" className="max-h-72 overflow-y-auto p-3">
      <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Sezioni</h2>
      <ul className="flex flex-col gap-0.5">
        {sections.map((s) => {
          const active = time >= s.start_s && time < s.end_s;
          return (
            <li key={s.id} className={`flex items-center gap-2 rounded-md px-2 py-1 ${active ? "bg-raised" : ""}`}>
              <span aria-hidden="true" className="size-2.5 shrink-0 rounded-sm" style={{ background: s.color }} />
              <button
                type="button"
                onClick={() => onSeek(s.start_s)}
                aria-current={active ? "true" : undefined}
                className="min-w-0 flex-1 truncate text-left text-sm"
              >
                {s.name}
              </button>
              <span className="font-mono text-xs text-ink-muted">{formatDuration(s.start_s)}</span>
              <button
                type="button"
                onClick={() => onLoop(s.start_s, s.end_s)}
                aria-label={`Ripeti la sezione ${s.name}`}
                title="Ripeti la sezione"
                className="rounded px-1 text-xs text-ink-muted hover:bg-raised hover:text-ink"
              >
                ↻
              </button>
            </li>
          );
        })}
      </ul>
    </nav>,
    target,
  );
}
