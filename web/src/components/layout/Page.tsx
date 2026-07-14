import type { ReactNode } from "react"
import { Inbox, LoaderCircle } from "lucide-react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export function Page({ children, className, size = "wide" }: { children: ReactNode; className?: string; size?: "narrow" | "medium" | "wide" }) {
  return (
    <main className={cn(
      "mx-auto w-full space-y-7 px-4 py-5 sm:px-6 sm:py-8",
      size === "narrow" && "max-w-3xl",
      size === "medium" && "max-w-5xl",
      size === "wide" && "max-w-7xl",
      className,
    )}>
      {children}
    </main>
  )
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary/80">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-[-0.025em] text-foreground sm:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function SectionHeader({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function LoadingPage({ label = "Loading" }: { label?: string }) {
  return (
    <Page size="medium" className="flex min-h-[50vh] items-center justify-center">
      <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />{label}</div>
    </Page>
  )
}

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: { label: string; onClick?: () => void; href?: string }; icon?: ReactNode }) {
  return (
    <Card className="border-dashed bg-card/35">
      <CardContent className="flex flex-col items-center py-14 text-center">
        <div className="mb-4 flex size-11 items-center justify-center rounded-2xl bg-muted text-muted-foreground">{icon ?? <Inbox className="size-5" />}</div>
        <h3 className="font-medium text-foreground">{title}</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
        {action?.href && <Button asChild className="mt-4"><Link to={action.href}>{action.label}</Link></Button>}
        {action?.onClick && <Button className="mt-4" onClick={action.onClick}>{action.label}</Button>}
      </CardContent>
    </Card>
  )
}
