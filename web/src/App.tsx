import { lazy, Suspense, useEffect, type ComponentType } from "react";
import {
  Bookmark,
  BookOpen,
  ChartNoAxesColumnIncreasing,
  Home,
  Search,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LoadingPage } from "@/components/layout/Page";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { updateHaltSupport } from "./lib/haltSupport";
import { ZH_FONTS, usePrefs } from "./lib/prefs";

const HomePage = lazy(() => import("./pages/HomePage"));
const JobsPage = lazy(() => import("./pages/JobsPage"));
const LibraryPage = lazy(() => import("./pages/LibraryPage"));
const ReviewPage = lazy(() => import("./pages/ReviewPage"));
const SavedPage = lazy(() => import("./pages/SavedPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const SeriesPage = lazy(() => import("./pages/SeriesPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const WatchPage = lazy(() => import("./pages/WatchPage"));
const WordPage = lazy(() => import("./pages/WordPage"));

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  matches?: string[];
}

const primaryNav: NavItem[] = [
  { to: "/", label: "Home", icon: Home },
  { to: "/library", label: "Library", icon: BookOpen, matches: ["/series/", "/watch/"] },
  { to: "/review", label: "Review", icon: ChartNoAxesColumnIncreasing },
  { to: "/saved", label: "Saved", icon: Bookmark },
  { to: "/search", label: "Search", icon: Search, matches: ["/word/"] },
];

const utilityNav: NavItem[] = [
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/admin", label: "Admin", icon: SlidersHorizontal },
];

export default function App() {
  const zhFont = usePrefs((p) => p.zhFont);
  useEffect(() => {
    const stack = (ZH_FONTS[zhFont] ?? ZH_FONTS.sans).stack;
    document.documentElement.style.setProperty("--font-zh", stack);
    void updateHaltSupport(stack);
  }, [zhFont]);

  return (
    <TooltipProvider delayDuration={300}>
      <Toaster
        theme="dark"
        position="bottom-center"
        offset={{ bottom: "calc(4.75rem + env(safe-area-inset-bottom))" }}
        mobileOffset={{ bottom: "calc(4.75rem + env(safe-area-inset-bottom))" }}
        toastOptions={{ style: { background: "#18201d", border: "1px solid rgb(255 255 255 / 0.1)", color: "#e7e5e4" } }}
      />
      <div className="min-h-screen pb-[calc(4.25rem+env(safe-area-inset-bottom))] md:pb-0">
        <header className="sticky top-0 z-40 h-[53px] border-b border-border/70 bg-background/82 px-3 backdrop-blur-xl supports-[backdrop-filter]:bg-background/72 sm:px-5">
          <div className="mx-auto flex h-full max-w-[1680px] items-center">
            <NavLink to="/" className="mr-5 flex items-center gap-2.5" aria-label="Immersion home">
              <span className="flex size-8 items-center justify-center rounded-xl bg-primary font-zh text-base font-bold text-primary-foreground shadow-lg shadow-primary/10">沉</span>
              <span className="text-sm font-semibold tracking-tight text-foreground">Immersion</span>
            </NavLink>

            <nav className="hidden h-full items-center gap-1 md:flex" aria-label="Main navigation">
              {primaryNav.map((item) => <DesktopNavItem key={item.to} item={item} />)}
            </nav>

            <div className="ml-auto flex items-center gap-1">
              <span className="mr-3 hidden items-center gap-2 text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground xl:flex">
                <i className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.65)]" /> Mandarin workspace
              </span>
              {utilityNav.map((item) => <UtilityNavItem key={item.to} item={item} />)}
            </div>
          </div>
        </header>

        <ErrorBoundary>
        <Suspense fallback={<LoadingPage />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/series/:id" element={<SeriesPage />} />
            <Route path="/watch/:id" element={<WatchPage />} />
            <Route path="/saved" element={<SavedPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/word/:id" element={<WordPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<JobsPage />} />
          </Routes>
        </Suspense>
        </ErrorBoundary>

        <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border/80 bg-background/92 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden" aria-label="Mobile navigation">
          <div className="mx-auto grid h-16 max-w-lg grid-cols-5 px-1.5">
            {primaryNav.map((item) => <MobileNavItem key={item.to} item={item} />)}
          </div>
        </nav>
      </div>
    </TooltipProvider>
  );
}

function useItemActive(item: NavItem): boolean {
  const { pathname } = useLocation();
  if (item.to === "/") return pathname === "/";
  return pathname === item.to || pathname.startsWith(`${item.to}/`) || !!item.matches?.some((path) => pathname.startsWith(path));
}

function DesktopNavItem({ item }: { item: NavItem }) {
  const active = useItemActive(item);
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      className={cn(
        "relative flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground",
        active && "bg-primary/10 text-primary",
      )}
    >
      <Icon className="size-3.5" />
      {item.label}
      {active && <span className="absolute inset-x-2 -bottom-[11px] h-0.5 rounded-full bg-primary" />}
    </NavLink>
  );
}

function MobileNavItem({ item }: { item: NavItem }) {
  const active = useItemActive(item);
  const Icon = item.icon;
  return (
    <NavLink to={item.to} className={cn("flex flex-col items-center justify-center gap-1 text-[10px] font-medium text-muted-foreground", active && "text-primary")}>
      <span className={cn("flex size-8 items-center justify-center rounded-xl transition-colors", active && "bg-primary/10")}><Icon className="size-[18px]" /></span>
      {item.label}
    </NavLink>
  );
}

function UtilityNavItem({ item }: { item: NavItem }) {
  const active = useItemActive(item);
  const Icon = item.icon;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="ghost" size="icon-sm" className={cn("text-muted-foreground", active && "bg-primary/10 text-primary")}>
          <NavLink to={item.to} aria-label={item.label}><Icon /></NavLink>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{item.label}</TooltipContent>
    </Tooltip>
  );
}
