// Full-width CJK punctuation carries ~half an em of designed-in blank; the
// `halt` OpenType feature swaps in half-width-advance alternates and .x token
// spans request it (index.css). But not every font implements halt — Noto CJK
// and Noto Serif SC do, Apple's PingFang and Kaiti don't — and an unsupported
// feature is a silent no-op, so subtitles there keep the trailing gap.
//
// Measure the active zh stack: render a run of full-width punctuation with and
// without halt and compare widths. No narrowing → flag <html class="no-halt">
// so the CSS can fall back to trailing-punctuation padding compensation.

const PROBE_TEXT = "。，、！？".repeat(4);

export async function updateHaltSupport(stack: string): Promise<void> {
  try {
    // make sure webfonts in the stack are loaded before measuring; don't hang
    // forever if a face never resolves
    await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 3000))]);
  } catch {
    // measurement below still works against whatever did load
  }
  const probe = document.createElement("span");
  probe.style.cssText =
    "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:nowrap;font-size:100px";
  probe.style.fontFamily = stack;
  probe.textContent = PROBE_TEXT;
  document.body.appendChild(probe);
  const full = probe.getBoundingClientRect().width;
  probe.style.fontFeatureSettings = '"halt" 1';
  const halted = probe.getBoundingClientRect().width;
  probe.remove();
  // supporting fonts shed ~25-50% of the run; ask only for a clear signal
  const supported = full - halted > full * 0.1;
  document.documentElement.classList.toggle("no-halt", !supported);
}
