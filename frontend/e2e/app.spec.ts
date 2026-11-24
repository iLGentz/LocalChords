import { expect, test, type Page } from "@playwright/test";

/**
 * Richiede un'istanza avviata con almeno un brano analizzato, senza modello Whisper e con
 * LRCLIB disattivato: per esempio il brano sintetico di `tests/synth.py` (progressione C-G-Am-F
 * in Do maggiore, 120 BPM).
 */

async function openFirstSong(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("[data-app-ready]")).toBeVisible();
  await page.getByRole("navigation", { name: "Brani" }).getByRole("button").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Tonalità", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
}

test("intestazione, stato del sistema e accessibilità di base", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Elaborazione")).toBeVisible();
  await expect(page.getByText("attiva")).toBeVisible();
  await expect(page.getByRole("link", { name: "Vai al contenuto" })).toBeAttached();
  await expect(page.getByRole("search")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Vai al contenuto" })).toBeFocused();
});

test("scheda del brano: analisi, accordi, mixer, testi, trasporto", async ({ page }) => {
  await openFirstSong(page);
  const chords = page.getByRole("region", { name: /Accordi/ }).or(page.locator("section[aria-labelledby='chords-title']"));
  for (const name of ["C", "G", "Am", "F"]) {
    await expect(chords.getByRole("button", { name, exact: true }).first()).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Mixer" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mute Mix completo" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Testo" })).toBeVisible();
  await expect(page.getByText(/serve il modello Whisper small/)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Sezioni del brano" })).toBeVisible();

  // play con la barra spaziatrice: il pulsante passa a "Pausa" e il tempo avanza
  const play = page.getByRole("region", { name: "Trasporto" }).getByRole("button", { name: /Play|Pausa/ });
  await expect(play).toHaveText(/Play/, { timeout: 20_000 });
  // il focus resta sul brano cliccato: su un pulsante lo Spazio lo attiva (scelta voluta)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Space");
  await expect(play).toHaveText(/Pausa/);
  await page.waitForTimeout(1200);
  await page.keyboard.press("Space");
  await expect(play).toHaveText(/Play/);
  await expect(page.getByRole("region", { name: "Trasporto" })).not.toContainText("0:00.0 /");
});

test("trasposizione, notazione italiana e capo aggiornano gli accordi", async ({ page }) => {
  await openFirstSong(page);
  const controls = page.getByRole("region", { name: "Trasposizione e visualizzazione" });
  const sheet = page.locator("section[aria-labelledby='chords-title']");

  await controls.getByRole("button", { name: "Un semitono sopra" }).click();
  await expect(controls.getByText("C → Db")).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Db", exact: false }).first()).toBeVisible();

  await controls.getByLabel("Notazione").selectOption("italian");
  await expect(sheet.getByText("Reb").first()).toBeVisible();

  await controls.getByLabel("Notazione").selectOption("american");
  await controls.getByRole("button", { name: "Originale" }).click();
  await controls.getByLabel("Capo").selectOption("2");
  await expect(sheet.getByText("Bb").first()).toBeVisible(); // C con capo 2 → forma di Bb
  await controls.getByLabel("Capo").selectOption("0");
});

test("diagrammi per chitarra, ukulele e pianoforte", async ({ page }) => {
  await openFirstSong(page);
  const diagrams = page.getByRole("list", { name: "Diagrammi degli accordi" });
  await expect(diagrams.getByRole("img").first()).toBeVisible();
  const controls = page.getByRole("region", { name: "Trasposizione e visualizzazione" });
  await controls.getByLabel("Strumento").selectOption("piano");
  await expect(diagrams.getByRole("img", { name: /note 3/ }).first()).toBeVisible();
  await controls.getByLabel("Strumento").selectOption("guitar");
});

test("export TXT e PDF scaricati dal browser", async ({ page }) => {
  await openFirstSong(page);
  const panel = page.locator("section[aria-labelledby='export-title']");
  for (const [button, ext] of [["TXT", ".txt"], ["PDF", ".pdf"]] as const) {
    const download = page.waitForEvent("download");
    await panel.getByRole("button", { name: button, exact: true }).click();
    expect((await download).suggestedFilename()).toMatch(new RegExp(`\\${ext}$`));
  }
});

test("tema chiaro e pagina impostazioni", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("combobox", { name: /^Tema/ }).selectOption("light");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.getByRole("combobox", { name: /^Tema/ }).selectOption("dark");
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("combobox", { name: /^Tema/ }).selectOption("cyber");
  await expect(page.locator("html")).toHaveClass(/cyber/);
  await expect(page.locator("html")).toHaveClass(/dark/); // il Cyber resta un tema scuro
  await page.getByRole("button", { name: "Impostazioni" }).first().click();
  // il tema si sceglie anche dalle Impostazioni
  await page.getByRole("radio", { name: /Chiaro/ }).check();
  await expect(page.locator("html")).not.toHaveClass(/dark|cyber/);
  await page.getByRole("radio", { name: /Scuro/ }).check();
  await expect(page.getByRole("heading", { name: "Elaborazione e hardware" })).toBeVisible();
  await expect(page.getByText("Leggero", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Modelli di separazione" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Spazio su disco" })).toBeVisible();
});
