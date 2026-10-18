import { BookOpen, Headphones, PencilLine } from "lucide-react";
import { ToggleGroup } from "radix-ui";

import { STUDY_MODES, type StudyMode } from "./studyMode";

const icons = { read: BookOpen, listen: Headphones, dictate: PencilLine };

export default function StudyModeSelector({ value, onChange }: { value: StudyMode; onChange: (mode: StudyMode) => void }) {
  return (
    <section className="study-mode-panel mb-3 shrink-0 rounded-2xl border border-border bg-card/80 p-3 sm:flex sm:items-center sm:gap-5" aria-label="Study mode">
      <ToggleGroup.Root type="single" value={value} onValueChange={(next) => {
        if (STUDY_MODES.some((mode) => mode.value === next)) onChange(next as StudyMode);
      }} aria-label="Choose how to study" className="grid shrink-0 grid-cols-3 gap-1 rounded-xl bg-background p-1">
        {STUDY_MODES.map((mode) => {
          const Icon = icons[mode.value];
          return <ToggleGroup.Item key={mode.value} value={mode.value} aria-describedby="study-mode-description" className="flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary data-[state=on]:bg-primary/15 data-[state=on]:text-primary"><Icon className="size-4" />{mode.label}</ToggleGroup.Item>;
        })}
      </ToggleGroup.Root>
      <p id="study-mode-description" className="mt-3 text-sm leading-relaxed text-muted-foreground sm:mt-0" aria-live="polite">{STUDY_MODES.find((mode) => mode.value === value)?.description}</p>
    </section>
  );
}
