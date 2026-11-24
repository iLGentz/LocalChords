import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeChoice = "dark" | "light" | "cyber" | "system";
export type ResolvedTheme = "dark" | "light" | "cyber";

export const THEME_LABEL: Record<ThemeChoice, string> = {
  dark: "Scuro",
  light: "Chiaro",
  cyber: "Cyber",
  system: "Sistema",
};

const STORAGE_KEY = "localchords.theme";
const CHOICES = Object.keys(THEME_LABEL) as ThemeChoice[];

interface ThemeState {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (c: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeState>({ choice: "dark", resolved: "dark", setChoice: () => undefined });

function readChoice(): ThemeChoice {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return CHOICES.includes(v as ThemeChoice) ? (v as ThemeChoice) : "dark";
  } catch {
    return "dark";
  }
}

function systemTheme(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/**
 * Il tema cyber è un tema scuro: tiene anche la classe .dark, così le varianti `dark:` di
 * Tailwind e shadcn restano valide, e aggiunge .cyber che ridefinisce palette e pannelli.
 */
function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved !== "light");
  root.classList.toggle("cyber", resolved === "cyber");
}

/** Applica il tema prima del primo render, per evitare lampi di colore. */
export function applyInitialTheme(): void {
  const choice = readChoice();
  applyTheme(choice === "system" ? systemTheme() : choice);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readChoice);
  const [system, setSystem] = useState<"dark" | "light">(systemTheme);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = (): void => setSystem(mq.matches ? "light" : "dark");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const resolved: ResolvedTheme = choice === "system" ? system : choice;
  useEffect(() => applyTheme(resolved), [resolved]);

  const value = useMemo<ThemeState>(
    () => ({
      choice,
      resolved,
      setChoice: (c) => {
        setChoiceState(c);
        try {
          window.localStorage.setItem(STORAGE_KEY, c);
        } catch {
          /* storage non disponibile: vale per la sessione */
        }
      },
    }),
    [choice, resolved],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  return useContext(ThemeContext);
}
