import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { applyInitialTheme, ThemeProvider } from "@/hooks/useTheme";
import "@/index.css";

applyInitialTheme();

const root = document.getElementById("root");
if (!root) throw new Error("Elemento #root mancante");

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
