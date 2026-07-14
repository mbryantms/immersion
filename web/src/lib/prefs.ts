// Player/display preferences, persisted to localStorage.

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SubtitleMode = "off" | "zh" | "dual";
export type PinyinStyle = "marks" | "numbers";

// bundled or reliably-installed CJK stacks the user can pick from
export const ZH_FONTS: Record<string, { label: string; stack: string }> = {
  sans: { label: "Sans 黑体 (default)", stack: '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif' },
  wenkai: { label: "LXGW WenKai 霞鹜文楷", stack: '"LXGW WenKai", "Kaiti SC", "KaiTi", serif' },
  serif: { label: "Serif 宋体", stack: '"Noto Serif SC", "Songti SC", "SimSun", serif' },
  kai: { label: "Kai 楷体 (system)", stack: '"Kaiti SC", "KaiTi", "STKaiti", "LXGW WenKai", serif' },
};

interface Prefs {
  subtitleMode: SubtitleMode;
  toneColors: boolean;
  traditional: boolean;
  pinyin: boolean; // global pinyin ruby (discouraged; per-word tap is the norm)
  pinyinStyle: PinyinStyle; // dictionary pinyin display: tone marks vs numbers
  zhFont: keyof typeof ZH_FONTS;
  pauseAfter: boolean;
  pauseAfterDelayMs: number; // auto-resume delay; 0 = wait for keypress
  prerollMs: number;
  rate: number;
  fontScale: number;
  transcriptFontScale: number;
  set: (p: Partial<Prefs>) => void;
}

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      subtitleMode: "zh",
      toneColors: true,
      traditional: false,
      pinyin: false,
      pinyinStyle: "marks",
      zhFont: "sans",
      pauseAfter: false,
      pauseAfterDelayMs: 0,
      prerollMs: 300,
      rate: 1.0,
      fontScale: 1.0,
      transcriptFontScale: 1.0,
      set: (p) => set(p),
    }),
    { name: "immersion-prefs" },
  ),
);

export const cycleSubtitleMode = (m: SubtitleMode): SubtitleMode =>
  m === "off" ? "zh" : m === "zh" ? "dual" : "off";
