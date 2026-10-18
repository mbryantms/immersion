import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";
import { sceneRoutes } from "./scene-fixture";

async function fakeMicrophone(page: Page) {
  await page.addInitScript(() => {
    const state = { mode: "ok", calls: 0, stopped: 0, pending: null as null | (() => void) };
    (window as any).mic = state;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: () => {
      state.calls++;
      const stream = { getTracks: () => [{ stop: () => state.stopped++ }] };
      if (state.mode === "denied") return Promise.reject(new DOMException("Denied", "NotAllowedError"));
      if (state.mode === "pending") return new Promise((resolve) => { state.pending = () => resolve(stream); });
      return Promise.resolve(stream);
    } } });
    class Recorder {
      static isTypeSupported() { return true; }
      state = "inactive"; mimeType = "audio/webm;codecs=opus";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() { this.state = "recording"; }
      stop() { this.state = "inactive"; queueMicrotask(() => {
        const data = state.mode === "empty" ? new Blob([]) : state.mode === "oversize" ? new Blob([new Uint8Array(8*1024*1024+1)]) : new Blob(["synthetic browser capture"], { type: this.mimeType });
        this.ondataavailable?.({ data }); this.onstop?.();
      }); }
    }
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: Recorder });
  });
}

async function recordTake(page: Page, again = false) {
  await page.getByRole("button", { name: again ? "Record another take" : "Record my voice", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stop and save take" })).toBeVisible();
  await page.getByRole("button", { name: "Stop and save take" }).click();
  await expect(page.getByText("Saved in this browser for this source snapshot.")).toBeVisible();
}

test("shadowing saves locally, reloads, downloads, retains failed takes and removes them", async ({ page }, info) => {
  await fakeMicrophone(page); await sceneRoutes(page);
  const apiBodies: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/")) apiBodies.push(request.postData() ?? ""); });
  await page.goto("/scenes/1");
  expect(await page.evaluate(() => (window as any).mic.calls)).toBe(0);
  await recordTake(page);
  expect(await page.evaluate(() => (window as any).mic.stopped)).toBe(1);
  await page.reload();
  const audio = page.getByRole("region", { name: "Your voice recording" });
  await expect(audio).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download take" }).click();
  expect((await download).suggestedFilename()).toBe("immersion-scene-1-take.webm");
  for (const mode of ["denied", "empty", "oversize"]) {
    await page.evaluate((value) => { (window as any).mic.mode = value; }, mode);
    await page.getByRole("button", { name: "Record another take", exact: true }).click();
    if (mode !== "denied") await page.getByRole("button", { name: "Stop and save take" }).click();
    await expect(page.getByRole("alert")).toContainText(/previous.*take.*retained/i);
    await expect(audio).toBeVisible();
    await expect(page.getByRole("button", { name: "Record another take", exact: true })).toBeEnabled();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id, nodes }) => ({ id, details: nodes.map((node) => node.failureSummary) }))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(page.getByText("Saved in this browser for this source snapshot.")).toBeVisible();
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("shadowing-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Remove take", exact: true }).click();
  await expect(audio).toHaveCount(0); await page.reload(); await expect(audio).toHaveCount(0);
  expect(apiBodies.join(" ")).not.toContain("synthetic browser capture");
  expect(apiBodies.join(" ")).not.toContain("base64");
});

test("cancelled permission and SPA navigation release late or active microphone streams", async ({ page }) => {
  await fakeMicrophone(page); await sceneRoutes(page); await page.goto("/scenes/1");
  await page.evaluate(() => { (window as any).mic.mode = "pending"; });
  await page.getByRole("button", { name: "Record my voice", exact: true }).click();
  await page.getByRole("button", { name: "Cancel recording", exact: true }).click();
  await page.evaluate(() => (window as any).mic.pending());
  await expect.poll(() => page.evaluate(() => (window as any).mic.stopped)).toBe(1);
  await expect(page.getByRole("region", { name: "Your voice recording" })).toHaveCount(0);
  await page.evaluate(() => { (window as any).mic.mode = "ok"; });
  await recordTake(page);
  await page.getByRole("button", { name: "Record another take", exact: true }).click();
  await page.getByRole("button", { name: "Cancel recording", exact: true }).click();
  await expect(page.getByText("Saved in this browser for this source snapshot.")).toBeVisible();
  await page.getByRole("button", { name: "Record another take", exact: true }).click();
  await page.getByRole("button", { name: "Continue: Clarify", exact: true }).click();
  await page.getByRole("button", { name: "Continue: Less support", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).mic.stopped)).toBe(4);
  await expect(page.getByRole("button", { name: "Record my voice", exact: true })).toHaveCount(0);
});

async function openExplanation(page: Page) {
  await page.goto("/watch/1");
  await page.locator("video").evaluate((element: HTMLVideoElement) => { element.currentTime = .1; element.dispatchEvent(new Event("timeupdate")); });
  await page.getByRole("button", { name: "Explain", exact: true }).click();
  return page.getByRole("dialog");
}
const core = { artifact_id: 1, accepted: null, prompt_version: "4", natural: "Study, then study again.", literal: "study again study", structure: "A repeated action.", words: [{ zh: "学习", role: "action" }, { zh: "再学习", role: "repetition" }], particles: [], pinyin: "xué xí", hsk: { level: 1, offlist: [] }, provider: "test", model: "fixture", created_at: "2026-10-18T00:00:00Z" };

test("explanations require explicit extras and persistent rejection before regeneration", async ({ page }, info) => {
  let extras = 0, calls = 0, rejected = false, retries = 0;
  await page.route("**/api/sentences/1/explain**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("explain-extras")) {
      extras++; await route.fulfill({ json: { artifact_id: 2, pronunciation: [], nuance: "", variations: [], pattern: null, mistakes: [], provider: "test" } }); return;
    }
    calls++; await route.fulfill(rejected ? { status: 409, json: { detail: { code: "artifact_rejected", artifact_id: 1 } } } : { json: { ...core, artifact_id: retries ? 3 : 1 } });
  });
  await page.route("**/api/ai-artifacts/1/feedback", async (route) => { rejected = true; expect(route.request().postDataJSON().accepted).toBe(false); await route.fulfill({ json: { accepted: false } }); });
  await page.route("**/api/ai-artifacts/1/retry", async (route) => { retries++; rejected = false; await route.fulfill({ json: { generation: 1 } }); });
  let dialog = await openExplanation(page);
  await expect(dialog.getByText("A repeated action.")).toBeVisible(); expect(extras).toBe(0);
  await dialog.getByRole("button", { name: "Request more detail" }).click();
  await expect.poll(() => extras).toBe(1);
  await expect(dialog.getByRole("region", { name: "Review AI extra detail" })).toBeVisible();
  await expect(dialog.getByRole("region", { name: "Review AI core explanation" })).toBeVisible();
  await dialog.getByRole("region", { name: "Review AI core explanation" }).getByRole("button", { name: "Reject core explanation", exact: true }).click();
  await expect(dialog.getByText("A repeated action.")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Explain", exact: true }).click();
  dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Request another attempt" })).toBeVisible();
  await dialog.getByRole("button", { name: "Request another attempt" }).click();
  await expect(dialog.getByText("A repeated action.")).toBeVisible();
  expect(retries).toBe(1); expect(calls).toBe(3); expect(extras).toBe(1);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id, nodes }) => ({ id, details: nodes.map((node) => node.failureSummary) }))).toEqual([]);
  await page.screenshot({ path: info.outputPath("explanation-review.png"), fullPage: true });
});

test("closing a pending explanation cancels its exact server request and never chains extras", async ({ page }) => {
  let requestId = "", cancelled = "", extras = 0;
  await page.route("**/api/sentences/1/explain**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("explain-extras")) { extras++; await route.fulfill({ json: {} }); return; }
    requestId = url.searchParams.get("request_id")!;
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ json: core }).catch(() => {});
  });
  await page.route("**/api/ai-requests/*", async (route) => { cancelled = route.request().url().split("/").at(-1)!; await route.fulfill({ json: { cancelled: true } }); });
  await openExplanation(page);
  await expect.poll(() => requestId).not.toBe("");
  await page.keyboard.press("Escape");
  await expect.poll(() => cancelled).toBe(requestId);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(extras).toBe(0);
});

test("AI prefetch is off on lookup and settings persist explicit opt-in", async ({ page }) => {
  let generations = 0, settings = { enabled: true, prefetch: false, provider_available: false };
  await page.route("**/api/sentences/*/explain**", async (route) => { generations++; await route.fulfill({ json: core }); });
  await page.route("**/api/ai-policy", async (route) => { if (route.request().method() === "PUT") settings = { ...settings, ...route.request().postDataJSON() }; await route.fulfill({ json: settings }); });
  await page.goto("/watch/1");
  await page.locator('[data-sentence-id="1"]').last().getByRole("button", { name: "Look up 学习" }).first().click();
  await expect(page.getByRole("dialog", { name: "Definition for 学习" })).toBeVisible();
  expect(generations).toBe(0);
  await page.goto("/settings");
  await expect(page.getByRole("switch", { name: "Prefetch explanations on word lookup" })).not.toBeChecked();
  await page.getByRole("switch", { name: "Prefetch explanations on word lookup" }).click();
  await expect.poll(() => settings.prefetch).toBe(true);
  await page.goto("/watch/1");
  await page.locator('[data-sentence-id="1"]').last().getByRole("button", { name: "Look up 学习" }).first().click();
  await expect.poll(() => generations).toBe(1);
});

test("quota failure leaves a downloadable take and preserves the previous stored recording", async ({ page }) => {
  await fakeMicrophone(page); await sceneRoutes(page); await page.goto("/scenes/1");
  await recordTake(page);
  await page.evaluate(() => { IDBObjectStore.prototype.put = () => { throw new DOMException("Full", "QuotaExceededError"); }; });
  await page.getByRole("button", { name: "Record another take", exact: true }).click();
  await page.getByRole("button", { name: "Stop and save take" }).click();
  await expect(page.getByRole("alert")).toContainText("previous stored take is retained");
  await expect(page.getByRole("link", { name: "Download take" })).toBeVisible();
  await expect(page.getByText("Available in this tab; download before leaving.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Saved in this browser for this source snapshot.")).toBeVisible();
});

test("failed AI core requests never start optional detail", async ({ page }) => {
  let extras = 0;
  await page.route("**/api/sentences/1/explain**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("explain-extras")) extras++;
    await route.fulfill({ status: 422, json: { detail: "Invalid explanation structure" } });
  });
  const dialog = await openExplanation(page);
  await expect(dialog.getByText(/Invalid explanation structure/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Try explanation again" })).toBeVisible();
  expect(extras).toBe(0);
});

test("native browser recording produces decodable local audio for comparison", async ({ page }) => {
  // Use the browser's real MediaRecorder/codec with a local oscillator stream.
  // This checks encoding/storage/playback without microphone permission or speech assessment.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => {
      const context = new AudioContext();
      const oscillator = context.createOscillator();
      const output = context.createMediaStreamDestination();
      oscillator.connect(output); oscillator.start(); await context.resume();
      output.stream.getAudioTracks()[0].addEventListener("ended", () => { oscillator.stop(); void context.close(); });
      return output.stream;
    } } });
  });
  await sceneRoutes(page); await page.goto("/scenes/1");
  await page.getByRole("button", { name: "Record my voice", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Recording 1 / 60 seconds" })).toBeVisible();
  await page.getByRole("button", { name: "Stop and save take" }).click();
  await expect(page.getByText("Saved in this browser for this source snapshot.")).toBeVisible();
  await page.reload();
  const audio = page.getByLabel("Play your recorded take");
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.readyState)).toBeGreaterThanOrEqual(1);
  expect(await audio.evaluate((element: HTMLAudioElement) => element.error)).toBeNull();
  await audio.evaluate((element: HTMLAudioElement) => element.play());
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0);
  await audio.evaluate((element: HTMLAudioElement) => element.pause());
});
