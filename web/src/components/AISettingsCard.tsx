import { useMutation, useQueryClient } from "@tanstack/react-query";
import { put } from "../api/client";
import { useAIPolicy, type AIPolicy } from "../api/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Switch } from "./ui/switch";

export default function AISettingsCard() {
  const policy = useAIPolicy();
  const queryClient = useQueryClient();
  const save = useMutation({ mutationFn: (body: { enabled: boolean; prefetch: boolean }) => put<AIPolicy>("/ai-policy", body), onSuccess: (value) => queryClient.setQueryData(["ai-policy"], value) });
  const change = (patch: Partial<AIPolicy>) => { if (policy.data) save.mutate({ enabled: policy.data.enabled, prefetch: policy.data.prefetch, ...patch }); };
  return <Card><CardHeader><CardTitle className="text-base">Optional AI assistance</CardTitle><CardDescription>Core playback, dictionary lookup and practice work without AI. The configured CLI may contact a remote service with sentence text and its translation; microphone recordings stay in your browser.</CardDescription></CardHeader><CardContent className="space-y-4">
    <div className="flex items-center justify-between gap-4"><label htmlFor="ai-enabled" className="text-sm font-medium">Allow AI generation</label><Switch id="ai-enabled" checked={!!policy.data?.enabled} disabled={!policy.data || save.isPending} onCheckedChange={(enabled) => change({ enabled })} /></div>
    <div className="flex items-center justify-between gap-4"><div><label htmlFor="ai-prefetch" className="text-sm font-medium">Prefetch explanations on word lookup</label><p className="mt-1 text-xs text-muted-foreground">Off by default. Opt in to generate a core explanation before you select Explain; busy work is skipped. Additional examples always need a separate request.</p></div><Switch id="ai-prefetch" checked={!!policy.data?.prefetch} disabled={!policy.data?.enabled || save.isPending} onCheckedChange={(prefetch) => change({ prefetch })} /></div>
    <p className="text-xs text-muted-foreground">{policy.data?.provider_available ? "Provider CLI detected; its authentication and model configuration determine availability." : "Provider CLI is unavailable. Previously cached explanations remain readable when AI assistance is enabled."} Disabling generation stops API requests and prevents new translation batches; an already running worker batch may finish.</p>
    {(policy.isError || save.isError) && <p role="alert" className="text-sm text-amber-200">Could not load or save AI preferences. Try again.</p>}
  </CardContent></Card>;
}
