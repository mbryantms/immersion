import AxeBuilder from "@axe-core/playwright";
import { test, expect, words } from "./fixtures";

test("corrections save, reset, restore, refresh the transcript, and preserve focus", async ({ page }, info) => {
  const source = { zh: "学习，再学习。", en: "Study, then study again.", t0_ms: 0, t1_ms: 3500 };
  const initial = { ...source, words };
  let current = { ...initial };
  const states: typeof current[] = [];
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/sentences/1/corrections", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON(); requests.push(body);
      if (body.reset) current = { ...initial };
      else if (body.restore_revision) current = { ...states[body.restore_revision - 1] };
      else current = { ...current, ...body };
      states.push({ ...current });
    }
    await route.fulfill({ json: { source, current, revision: states.length, history: states.map((_, index) => ({ revision: index + 1, action: "edit", created_at: "2026-10-18" })) } });
  });
  await page.route("**/api/items/1/sentences", async (route) => {
    await route.fulfill({ json: { item_id: 1, zh_offset_ms: 0, sentences: [{ id: 1, ord: 0, ...current, t0: current.t0_ms, t1: current.t1_ms, conf: 1, tr: null }] } });
  });
  await page.goto("/watch/1");
  const edit = page.getByRole("button", { name: "Correct sentence 1" });
  await edit.click();
  const dialog = page.getByRole("dialog", { name: "Correct this line" });
  await expect(dialog).toBeVisible();
  await page.getByRole("textbox", { name: "English meaning" }).fill("My contextual translation.");
  await page.getByRole("button", { name: "Save correction", exact: true }).click();
  await expect(dialog.getByText(/Revision 1\./)).toBeVisible();
  await page.getByRole("button", { name: "Reset to source" }).click();
  await expect(page.getByRole("textbox", { name: "English meaning" })).toHaveValue(source.en);
  await page.getByText("Original source and correction history", { exact: true }).click();
  await page.getByRole("button", { name: "Restore revision 1", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "English meaning" })).toHaveValue("My contextual translation.");
  expect(requests.map((body) => body.expected_revision)).toEqual([0, 1, 2]);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(accessibility.violations.map((item) => ({ id: item.id, details: item.nodes.map((node) => node.failureSummary) }))).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("correction-editor-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await expect(edit).toBeFocused();
  await page.getByRole("button", { name: "Reveal translation", exact: true }).click();
  await expect(page.getByRole("complementary").getByText("My contextual translation.", { exact: true })).toBeVisible();
});

test("a stale correction keeps the draft until the learner reloads", async ({ page }) => {
  let latest = false;
  await page.route("**/api/sentences/1/corrections", async (route) => {
    if (route.request().method() === "PATCH") {
      latest = true;
      await route.fulfill({ status: 409, json: { detail: "This line changed. Reload its history before saving." } });
    } else await route.fulfill({ json: { revision: latest ? 2 : 0, source: { zh: "学习", en: "Original", t0_ms: 0, t1_ms: 3500 }, current: { zh: "学习", en: latest ? "Other tab" : "Original", t0_ms: 0, t1_ms: 3500, words: [] }, history: [] } });
  });
  await page.goto("/watch/1");
  await page.getByRole("button", { name: "Correct sentence 1" }).click();
  const meaning = page.getByRole("textbox", { name: "English meaning" });
  await meaning.fill("My unsaved draft");
  await page.getByRole("button", { name: "Save correction", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("409");
  await expect(meaning).toHaveValue("My unsaved draft");
  await page.getByRole("button", { name: "Reload latest line" }).click();
  await expect(meaning).toHaveValue("Other tab");
});

test("subtitle selection and playback repair show actionable progress", async ({ page }) => {
  const paths: string[] = [];
  let selection: Record<string, unknown> | undefined;
  await page.route("**/api/items/1/tracks", async (route) => { paths.push("tracks"); selection = route.request().postDataJSON(); await route.fulfill({ json: { queued: true } }); });
  await page.route("**/api/items/1/repair-media", async (route) => { paths.push("repair"); await route.fulfill({ json: { queued: true } }); });
  await page.goto("/watch/1");
  await page.getByText("Subtitle sources and playback repair", { exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Chinese subtitle source" })).toHaveValue("1");
  await page.getByRole("button", { name: "Use selected tracks" }).click();
  await expect(page.getByText("Updating the transcript. Your source selections are saved.")).toBeVisible();
  expect(selection).toEqual({ zh_track_id: 1, en_track_id: null });
  await page.getByRole("button", { name: "Repair playback" }).click();
  await expect(page.getByText(/Playback repair queued/)).toBeVisible();
  expect(paths).toEqual(["tracks", "repair"]);
});

test("checked dictation keeps its original target after a source edit", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("dict:1", JSON.stringify({ version: 2, attempts: { 1: { typed: "学习，再学习。", expected: "学习，再学习。", sourceRevision: 0, checked: true, scriptPolicy: "source" } } }));
  });
  await page.route("**/api/items/1/sentences", async (route) => {
    await route.fulfill({ json: { item_id: 1, zh_offset_ms: 0, sentences: [{ id: 1, ord: 0, zh: "银行。", t0: 0, t1: 3500, en: "Bank.", tr: null, conf: 1, words: [{ t: "银行", type: "zh", lex: 3 }] }] } });
  });
  await page.goto("/watch/1");
  await page.getByRole("radio", { name: "Dictate", exact: true }).click();
  await expect(page.getByLabel("100 percent character accuracy")).toBeVisible();
  await expect(page.getByText(/This line changed after your attempt/)).toBeVisible();
});
