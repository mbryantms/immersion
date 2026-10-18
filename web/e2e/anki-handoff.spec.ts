import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";
import { ankiRoutes } from "./anki-fixture";

async function preview(page: import("@playwright/test").Page) {
  await page.goto("/exports");
  await page.getByRole("checkbox", { name: /学习/ }).check();
  await page.getByRole("button", { name: "Preview 1 selected for Anki" }).click();
  return page.getByRole("dialog", { name: "Export to Anki" });
}

test("export setup loads existing choices and maps a different note type without changing templates", async ({ page }, info) => {
  const state = await ankiRoutes(page);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Check Anki and load choices" }).click();
  await page.getByRole("combobox", { name: "Note type", exact: true }).selectOption("Basic");
  await page.getByText("Map export fields", { exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Anki field for Chinese text (simplified)", exact: true })).toHaveValue("Front");
  await expect(page.getByRole("combobox", { name: "Anki field for Selected meaning", exact: true })).toHaveValue("Back");
  await expect(page.getByRole("button", { name: "Save Anki export setup" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /I reviewed the note type/ }).check();
  await page.getByRole("button", { name: "Save Anki export setup" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Anki export setup saved." })).toBeVisible();
  expect(state.profileWrites[0].fields).toEqual({ Simplified: "Front", Meaning: "Back" });
  expect(state.profileWrites[0].word_tts).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map((node) => node.failureSummary) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("anki-settings-mobile.png"), fullPage: true });
});

test("completed reviews remain in the inbox through defer, reload and restore", async ({ page }) => {
  await ankiRoutes(page); await page.goto("/exports");
  await page.getByRole("button", { name: "Defer 学习", exact: true }).click();
  await expect(page.getByText("No completed reviews awaiting export.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Deferred 1", exact: true }).click();
  await expect(page.getByText("xue2 xi2", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Deferred 1", exact: true }).click();
  await page.getByRole("button", { name: "Restore 学习", exact: true }).click();
  await page.getByRole("button", { name: "Ready 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "Defer 学习", exact: true })).toBeVisible();
});

test("a lost submission reply survives closing and reload with the same UUID and meaning", async ({ page }) => {
  const state = await ankiRoutes(page, { lost: true });
  let dialog = await preview(page);
  await dialog.getByRole("textbox", { name: "Meaning for 学习" }).fill("study this expression");
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("reply was not confirmed");
  await dialog.getByRole("button", { name: "Close export", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Submissions awaiting confirmation" })).toBeVisible();
  await page.getByRole("button", { name: "Retry same submission", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Submissions awaiting confirmation" })).toHaveCount(0);
  expect(state.submitted).toBe(1); expect(state.requests).toHaveLength(2);
  expect(state.requests[0]).toEqual(state.requests[1]);
  expect(state.requests[0].entries[0].meaning).toBe("study this expression");
  await expect(page.getByRole("region", { name: "Export submission 10" })).toBeVisible();
});

test("uncertain note delivery needs reconciliation or an explicit checked retry", async ({ page }, info) => {
  const state = await ankiRoutes(page);
  const dialog = await preview(page);
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Accepted export status" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close export", exact: true }).click();
  state.batches[0].status = "done"; state.batches[0].items[0].status = "uncertain"; state.batches[0].items[0].error = "Anki did not confirm whether the note was added.";
  await page.reload();
  await expect(page.getByRole("button", { name: "Retry unconfirmed 学习", exact: true })).toBeDisabled();
  await page.getByText("Reviewed fields and source for 学习", { exact: true }).click();
  await expect(page.getByText("Find this exact note in Anki with: tag:immersion-id-fixture", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map((node) => node.failureSummary) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("anki-inbox-mobile.png"), fullPage: true });
  state.noteExists = true;
  await page.getByRole("button", { name: "Check Anki for 学习", exact: true }).click();
  await expect(page.getByText(/Confirmed in Anki/)).toBeVisible();
  expect(state.reconciles).toBe(1); expect(state.submitted).toBe(1);
  await expect(page.getByRole("button", { name: "Retry unconfirmed 学习", exact: true })).toHaveCount(0);
});

test("missing note types block export and keep setup reachable", async ({ page }) => {
  await ankiRoutes(page, { missing: true }); const dialog = await preview(page);
  await expect(dialog.getByRole("alert")).toContainText("note type is missing");
  await expect(dialog.getByRole("button", { name: "Export 1 note", exact: true })).toHaveCount(0);
  await dialog.getByRole("link", { name: "Open Anki export setup" }).click();
  await expect(page).toHaveURL(/\/settings$/);
});

test("duplicate export is excluded until the learner intentionally allows another note", async ({ page }, info) => {
  const state = await ankiRoutes(page, { duplicate: true }); const dialog = await preview(page);
  await expect(dialog.getByRole("button", { name: "Export 0 notes", exact: true })).toBeDisabled();
  await dialog.getByRole("checkbox", { name: "Add another note for 学习", exact: true }).check();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  await page.screenshot({ path: info.outputPath("anki-preview-desktop.png"), fullPage: true });
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Accepted export status" })).toBeVisible();
  expect(state.requests[0].entries[0].allow_duplicate).toBe(true);
});

test("storage failure prevents an unrecoverable submission and retains its editable preview", async ({ page }) => {
  const state = await ankiRoutes(page); const dialog = await preview(page);
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException("Quota", "QuotaExceededError"); }; });
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  expect(state.submitted).toBe(0);
  await expect(dialog.getByRole("textbox", { name: "Meaning for 学习" })).toBeEnabled();
});

test("another add after uncertainty requires an explicit checked confirmation", async ({ page }) => {
  const state = await ankiRoutes(page); const dialog = await preview(page);
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Accepted export status" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close export", exact: true }).click();
  state.batches[0].status = "done"; state.batches[0].items[0].status = "uncertain";
  await page.reload();
  const retry = page.getByRole("button", { name: "Retry unconfirmed 学习", exact: true });
  await expect(retry).toBeDisabled();
  await page.getByRole("checkbox", { name: /I checked Anki for 学习/ }).check();
  await retry.click();
  await expect.poll(() => state.requests.some((request) => request.confirm_no_note === true)).toBe(true);
});

test("export preview actions remain reachable at 320px with a scrollable body", async ({ page }) => {
  await ankiRoutes(page); await page.setViewportSize({ width: 320, height: 568 });
  const dialog = await preview(page);
  await expect(dialog.getByRole("button", { name: "Export 1 note", exact: true })).toBeInViewport();
  await expect(dialog.getByRole("button", { name: "Close export", exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("long saved sentences and recovery labels do not overflow the mobile inbox", async ({ page }) => {
  const state = await ankiRoutes(page); const dialog = await preview(page);
  await dialog.getByRole("button", { name: "Export 1 note", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Accepted export status" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close export", exact: true }).click();
  const sentence = "我每天都想学习一点新的中文，因为我希望能更好地理解这些故事。".repeat(4);
  state.batches[0].status = "done"; state.batches[0].items[0].status = "uncertain"; state.batches[0].items[0].surface = sentence;
  await page.route("**/api/anki/inbox?**", (route) => route.fulfill({ json: { counts: { ready: 1, deferred: 0 }, next_cursor: null, items: [{ id: 1, surface: sentence, kind: "sentence", selected_reading: null, selected_meaning: null, attempt_id: 10, export_status: "uncertain" }] } }));
  await page.setViewportSize({ width: 320, height: 568 }); await page.reload();
  await expect(page.getByRole("heading", { name: "Anki export inbox" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: `Retry unconfirmed ${sentence}`, exact: true })).toBeDisabled();
  await page.getByRole("link", { name: `View export for ${sentence}`, exact: true }).click();
  await expect(page.locator("#export-attempt-10")).toBeFocused();
});
