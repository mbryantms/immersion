import { BookOpenText, Captions, Gauge, Palette, RotateCcw, Type } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { Page, PageHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { get } from "../api/client";
import { formatPinyin } from "../lib/pinyin";
import { ZH_FONTS, usePrefs, type PinyinStyle, type SubtitleMode } from "../lib/prefs";

interface DictionariesInfo {
  dictionaries: { name: string; entries: number; source: string }[];
  lexemes: number;
  oov_lexemes: number;
}

export default function SettingsPage() {
  const prefs = usePrefs();
  const { data: dictionaries } = useQuery({ queryKey: ["dictionaries"], queryFn: () => get<DictionariesInfo>("/dictionaries") });

  const reset = () => prefs.set({ subtitleMode: "zh", toneColors: true, traditional: false, pinyin: false, pinyinStyle: "marks", zhFont: "sans", pauseAfter: false, pauseAfterDelayMs: 0, prerollMs: 300, rate: 1, fontScale: 1, transcriptFontScale: 1 });

  return (
    <Page size="medium">
      <PageHeader eyebrow="Preferences" title="Shape your learning environment" description="These settings follow you across video, podcasts, transcripts, and dictionary views." actions={<Button variant="outline" onClick={reset}><RotateCcw />Restore defaults</Button>} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">
          <Card>
            <CardHeader><div className="flex items-center gap-2"><Palette className="size-4 text-primary" /><CardTitle className="text-base">Reading and subtitles</CardTitle></div><CardDescription>Typography and annotation choices for Mandarin text</CardDescription></CardHeader>
            <CardContent className="space-y-0 pt-2">
              <SettingRow label="Chinese typeface" hint="Applied everywhere Chinese text appears">
                <Select value={prefs.zhFont} onValueChange={(value) => prefs.set({ zhFont: value as keyof typeof ZH_FONTS })}><SelectTrigger className="w-full sm:w-64"><Type className="size-3.5" /><SelectValue /></SelectTrigger><SelectContent>{Object.entries(ZH_FONTS).map(([key, font]) => <SelectItem key={key} value={key}><span style={{ fontFamily: font.stack }}>{font.label}</span></SelectItem>)}</SelectContent></Select>
              </SettingRow>
              <SettingRow label="Subtitle size" hint={`${Math.round(prefs.fontScale * 100)}% · adapts further to screen size`}>
                <div className="flex w-full items-center gap-3 sm:w-64"><span className="text-xs text-muted-foreground">A</span><Slider min={0.75} max={1.5} step={0.05} value={[prefs.fontScale]} onValueChange={([value]) => prefs.set({ fontScale: value })} aria-label="Subtitle size" /><span className="text-lg text-muted-foreground">A</span></div>
              </SettingRow>
              <SettingRow label="Transcript text size" hint={`${Math.round(prefs.transcriptFontScale * 100)}% · also adjustable beside Follow in the player`}>
                <div className="flex w-full items-center gap-3 sm:w-64"><span className="text-xs text-muted-foreground">A</span><Slider min={0.85} max={1.6} step={0.05} value={[prefs.transcriptFontScale]} onValueChange={([value]) => prefs.set({ transcriptFontScale: value })} aria-label="Transcript text size" /><span className="text-xl text-muted-foreground">A</span></div>
              </SettingRow>
              <SettingRow label="Pinyin notation" hint={`Preview: ${formatPinyin("mo4 fang2", prefs.pinyinStyle)}`}>
                <Select value={prefs.pinyinStyle} onValueChange={(value) => prefs.set({ pinyinStyle: value as PinyinStyle })}><SelectTrigger className="w-full sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="marks">Tone marks · mò fáng</SelectItem><SelectItem value="numbers">Tone numbers · mo4 fang2</SelectItem></SelectContent></Select>
              </SettingRow>
              <SettingRow label="Tone colors" hint="Use the Pleco color palette on hanzi"><Switch checked={prefs.toneColors} onCheckedChange={(checked) => prefs.set({ toneColors: checked })} /></SettingRow>
              <SettingRow label="Traditional characters" hint="Prefer traditional forms when available"><Switch checked={prefs.traditional} onCheckedChange={(checked) => prefs.set({ traditional: checked })} /></SettingRow>
              <SettingRow label="Always show pinyin" hint="Useful early on; hiding it encourages character recognition"><Switch checked={prefs.pinyin} onCheckedChange={(checked) => prefs.set({ pinyin: checked })} /></SettingRow>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div className="flex items-center gap-2"><Gauge className="size-4 text-primary" /><CardTitle className="text-base">Player defaults</CardTitle></div><CardDescription>Starting behavior for each new listening session</CardDescription></CardHeader>
            <CardContent className="space-y-0 pt-2">
              <SettingRow label="Subtitle mode" hint="You can still cycle this from the player">
                <Select value={prefs.subtitleMode} onValueChange={(value) => prefs.set({ subtitleMode: value as SubtitleMode })}><SelectTrigger className="w-full sm:w-64"><Captions className="size-3.5" /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="off">Off</SelectItem><SelectItem value="zh">Chinese only</SelectItem><SelectItem value="dual">Chinese + English</SelectItem></SelectContent></Select>
              </SettingRow>
              <SettingRow label="Playback speed" hint="The player remembers later changes"><Select value={String(prefs.rate)} onValueChange={(value) => prefs.set({ rate: Number(value) })}><SelectTrigger className="w-full sm:w-64"><SelectValue /></SelectTrigger><SelectContent>{[0.6, 0.8, 1, 1.25].map((rate) => <SelectItem key={rate} value={String(rate)}>{rate}×</SelectItem>)}</SelectContent></Select></SettingRow>
              <SettingRow label="Pause after sentences" hint="Create retrieval time before the next line"><Switch checked={prefs.pauseAfter} onCheckedChange={(checked) => prefs.set({ pauseAfter: checked })} /></SettingRow>
              {prefs.pauseAfter && <SettingRow label="Resume behavior" hint="Wait for input or continue automatically"><Select value={String(prefs.pauseAfterDelayMs)} onValueChange={(value) => prefs.set({ pauseAfterDelayMs: Number(value) })}><SelectTrigger className="w-full sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">Wait for me</SelectItem><SelectItem value="1000">After 1 second</SelectItem><SelectItem value="2000">After 2 seconds</SelectItem><SelectItem value="3000">After 3 seconds</SelectItem></SelectContent></Select></SettingRow>}
              <SettingRow label="Sentence pre-roll" hint="Start slightly before a selected sentence"><Select value={String(prefs.prerollMs)} onValueChange={(value) => prefs.set({ prerollMs: Number(value) })}><SelectTrigger className="w-full sm:w-64"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">None</SelectItem><SelectItem value="300">300 ms</SelectItem><SelectItem value="500">500 ms</SelectItem><SelectItem value="800">800 ms</SelectItem></SelectContent></Select></SettingRow>
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-5 lg:sticky lg:top-20 lg:self-start">
          <Card className="overflow-hidden">
            <div className="bg-gradient-to-br from-primary/10 to-transparent p-5"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-primary/80">Live preview</p><p className={`font-zh text-xl leading-loose ${prefs.toneColors ? "tones" : ""}`} style={{ fontFamily: ZH_FONTS[prefs.zhFont].stack }}><span className="t4">沉</span><span className="t4">浸</span><span className="t2">式</span><span className="t2">学</span><span className="t2">习</span>让语言变得自然。</p><p className="mt-2 text-xs text-muted-foreground">Immersion makes language feel natural.</p></div>
          </Card>

          <Card>
            <CardHeader><div className="flex items-center gap-2"><BookOpenText className="size-4 text-primary" /><CardTitle className="text-sm">Dictionaries</CardTitle></div></CardHeader>
            <CardContent className="space-y-3 pt-2">
              {(dictionaries?.dictionaries ?? []).map((dictionary) => <div key={dictionary.name}><div className="flex items-center justify-between gap-2"><span className="text-sm">{dictionary.name}</span><Badge variant="secondary" className="tabular-nums">{dictionary.entries.toLocaleString()}</Badge></div><p className="mt-0.5 text-[10px] text-muted-foreground">{dictionary.source}</p></div>)}
              {dictionaries && <><Separator /><p className="text-xs leading-relaxed text-muted-foreground">{dictionaries.lexemes.toLocaleString()} words in your library lexicon<br />{dictionaries.oov_lexemes.toLocaleString()} names or OOV tokens</p></>}
            </CardContent>
          </Card>
        </aside>
      </div>
    </Page>
  );
}

function SettingRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div className="grid gap-3 border-b border-border py-4 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"><div><p className="text-sm font-medium">{label}</p>{hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}</div><div className="flex justify-start sm:justify-end">{children}</div></div>;
}
