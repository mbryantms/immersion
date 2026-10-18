export type StudyMode = "read" | "listen" | "dictate";

export const STUDY_MODES: { value: StudyMode; label: string; description: string }[] = [
  { value: "read", label: "Read", description: "Follow the Chinese text. Reveal pinyin or English when you need help." },
  { value: "listen", label: "Listen", description: "Listen without text. Reveal the transcript only when you need a hint." },
  { value: "dictate", label: "Dictate", description: "Replay a line and type what you hear. Answers stay hidden until you check." },
];

export function textIsVisible(mode: StudyMode, hint = false): boolean {
  return mode === "read" || (mode === "listen" && hint);
}

export function maskedParts(text: string, surface: string): string[] {
  return surface ? text.split(surface) : [text];
}
