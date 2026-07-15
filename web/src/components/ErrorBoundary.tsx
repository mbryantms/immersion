import { Component, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Last-resort catch for render/lazy-import throws — a broken route should
 *  show a way back, never a blank screen. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-lg font-semibold">Something broke on this page</p>
        <p className="max-w-md text-sm text-muted-foreground">{this.state.error.message}</p>
        <div className="flex gap-2">
          <Button onClick={() => this.setState({ error: null })}>Try again</Button>
          <Button variant="outline" onClick={() => window.location.assign("/")}>Go home</Button>
        </div>
      </div>
    );
  }
}

/** Inline failure state for a page whose main query errored. */
export function QueryError({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-lg font-semibold">Couldn't load this page</p>
      <p className="max-w-md text-sm text-muted-foreground">
        {message ?? "The server didn't respond. It may be restarting — try again in a moment."}
      </p>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}
