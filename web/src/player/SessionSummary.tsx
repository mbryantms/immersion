import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { KnowledgeStateName } from "../api/types";

export interface SessionLookup {
  lexemeId: number;
  surface: string;
  pinyin?: string;
  sentenceId: number;
}

interface Props {
  lookups: SessionLookup[];
  minutes: number;
  knowledge: Record<string, KnowledgeStateName>;
  savedLexemes: Set<number>;
  onSave: (selected: SessionLookup[]) => void;
  onClose: () => void;
}

/** End-of-session recap: what you looked up, with one-tap bulk save into the
 *  review funnel. No quiz, no streaks — just capture before it evaporates. */
export default function SessionSummary({ lookups, minutes, knowledge, savedLexemes, onSave, onClose }: Props) {
  // preselect words still unknown and not already saved
  const [selected, setSelected] = useState<Set<number>>(() => new Set(
    lookups
      .filter((l) => !savedLexemes.has(l.lexemeId))
      .filter((l) => ["new", "learning"].includes(knowledge[l.lexemeId] ?? "new"))
      .map((l) => l.lexemeId),
  ));

  const toggle = (lexemeId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lexemeId)) next.delete(lexemeId);
      else next.add(lexemeId);
      return next;
    });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Session summary</DialogTitle>
          <DialogDescription>
            {minutes >= 1 ? `${Math.round(minutes)} min of listening` : "A quick session"}
            {lookups.length
              ? ` · ${lookups.length} word${lookups.length === 1 ? "" : "s"} looked up`
              : " · no lookups — smooth sailing"}
          </DialogDescription>
        </DialogHeader>

        {lookups.length > 0 && (
          <div className="space-y-1">
            {lookups.map((lookup) => {
              const alreadySaved = savedLexemes.has(lookup.lexemeId);
              return (
                <label
                  key={lookup.lexemeId}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 transition hover:bg-white/[0.04]"
                >
                  <Checkbox
                    checked={selected.has(lookup.lexemeId)}
                    disabled={alreadySaved}
                    onCheckedChange={() => toggle(lookup.lexemeId)}
                  />
                  <span className="font-zh text-base text-stone-100">{lookup.surface}</span>
                  {lookup.pinyin && <span className="text-xs text-stone-500">{lookup.pinyin}</span>}
                  {alreadySaved && <span className="ml-auto text-[10px] text-teal-500">saved</span>}
                </label>
              );
            })}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {selected.size > 0 && (
            <Button onClick={() => onSave(lookups.filter((l) => selected.has(l.lexemeId)))}>
              Save {selected.size} word{selected.size === 1 ? "" : "s"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
