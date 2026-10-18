import { useMiningBudget } from "../components/MiningBudgetCard";
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

export interface SessionLookup {
  lexemeId: number;
  surface: string;
  pinyin?: string;
  sentenceId: number;
}

interface Props {
  lookups: SessionLookup[];
  minutes: number;
  savedLexemes: Set<number>;
  onSave: (selected: SessionLookup[]) => Promise<void>;
  onClose: () => void;
}

/** End-of-session recap: what you looked up, with one-tap bulk save into the
 *  review funnel. No quiz, no streaks — just capture before it evaporates. */
export default function SessionSummary({ lookups, minutes, savedLexemes, onSave, onClose }: Props) {
  const budget = useMiningBudget();
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [override, setOverride] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const selectedWords = lookups.filter((word) => selected.has(word.lexemeId) && !savedLexemes.has(word.lexemeId));
  const overBudget = budget.data ? selectedWords.length > budget.data.remaining : false;

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
      <DialogContent aria-busy={saving} className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Session summary</DialogTitle>
          <DialogDescription>
            {minutes >= 1 ? `${Math.round(minutes)} min of media activity` : "A quick session"}
            {lookups.length
              ? ` · ${lookups.length} word${lookups.length === 1 ? "" : "s"} looked up`
              : " · no dictionary lookups recorded"}
          </DialogDescription>
        </DialogHeader>

        <p className="text-xs leading-relaxed text-muted-foreground">Choose a few expressions you expect to reuse. Saving every unfamiliar word can overload review; a saved count is not a learning outcome.{budget.data ? ` ${budget.data.remaining} new cards remain within today's suggestion.` : ""}</p>
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
                    disabled={alreadySaved || saving}
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

        {overBudget && <label className="flex min-h-11 items-center gap-3 text-xs"><input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} />Save these choices beyond today's suggestion</label>}
        {error && <p role="alert" className="text-sm text-destructive">Some words could not be saved. Confirmed saves are retained; retry the remaining choices.</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {(selectedWords.length > 0 || saving) && (
            <Button disabled={saving || (overBudget && !override)} onClick={async () => { if (saving) return; setSaving(true); setError(false); try { await onSave(selectedWords); } catch { setError(true); } finally { setSaving(false); } }}>
              {saving ? "Saving…" : `Save ${selectedWords.length} word${selectedWords.length === 1 ? "" : "s"}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
