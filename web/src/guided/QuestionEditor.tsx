import { useState } from "react";
import type { GuidedScene } from "../api/types";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

export default function QuestionEditor({ scene, disabled, onSave }: { scene: GuidedScene; disabled: boolean; onSave: (question: Record<string, unknown>) => void }) {
  const [line, setLine] = useState(0);
  const [prompt, setPrompt] = useState("");
  const [category, setCategory] = useState("meaning");
  const [choices, setChoices] = useState(["", ""]);
  const [explanations, setExplanations] = useState(["", ""]);
  const [answer, setAnswer] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const valid = prompt.trim() && choices.every((choice) => choice.trim()) && explanations.every((choice) => choice.trim()) && choices[0].trim().toLocaleLowerCase() !== choices[1].trim().toLocaleLowerCase() && answer !== "" && reviewed;
  return <details className="rounded-xl border border-border p-4"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">Add or replace a local meaning question</summary>
    <div className="space-y-4 pt-3"><p className="text-xs leading-relaxed text-muted-foreground">For a teacher, study partner, or your own practice. Review the exact source and both explanations. A locally authored key is not externally validated, and its author has already seen the answer.</p>
      <label className="block space-y-2 text-sm"><span>Source evidence</span><select className="min-h-11 w-full max-w-full rounded-md border border-input bg-background p-2" value={line} onChange={(event) => setLine(Number(event.target.value))}>{scene.snapshot.lines.map((sentence, index) => <option key={sentence.id} value={index}>{sentence.zh}</option>)}</select></label>
      <label className="block space-y-2 text-sm"><span>Meaning contrast</span><select className="min-h-11 w-full rounded-md border border-input bg-background p-2" value={category} onChange={(event) => setCategory(event.target.value)}>{[["meaning", "Meaning"], ["agent_patient", "Who did what to whom"], ["negation", "Negation"], ["aspect", "Aspect and change"], ["result", "Result"], ["comparison", "Comparison"], ["paraphrase", "Paraphrase"]].map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
      <label className="block space-y-2 text-sm"><span>Question prompt</span><Input className="min-h-11" value={prompt} maxLength={1000} onChange={(event) => setPrompt(event.target.value)} /></label>
      {choices.map((choice, index) => <div key={index} className="space-y-3 rounded-lg bg-muted/40 p-3"><label className="block space-y-2 text-sm"><span>Choice {index+1}</span><Input className="min-h-11" value={choice} maxLength={500} onChange={(event) => setChoices((previous) => previous.map((old, i) => i === index ? event.target.value : old))} /></label><label className="block space-y-2 text-sm"><span>Explanation for choice {index+1}</span><textarea className="min-h-20 w-full rounded-md border border-input bg-transparent p-3" value={explanations[index]} maxLength={1000} onChange={(event) => setExplanations((previous) => previous.map((old, i) => i === index ? event.target.value : old))} /></label></div>)}
      <fieldset className="space-y-2"><legend className="text-sm font-medium">Correct choice</legend>{choices.map((_, index) => <label key={index} className="flex min-h-11 items-center gap-3 text-sm"><input type="radio" name="question-answer" checked={answer === String(index)} onChange={() => setAnswer(String(index))} />Choice {index+1}</label>)}</fieldset>
      <label className="flex min-h-11 items-start gap-3 text-xs leading-relaxed"><input className="mt-1" type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I checked the source, the correct answer and each distractor explanation for ambiguity.</label>
      <Button className="min-h-11" disabled={disabled || !valid || !scene.source_current} onClick={() => onSave({ category, prompt: prompt.trim(), passage: scene.snapshot.lines[line].zh, choices: choices.map((text, i) => ({ text: text.trim(), explanation: explanations[i].trim() })), answer: Number(answer) })}>Save reviewed question</Button>
    </div>
  </details>;
}
