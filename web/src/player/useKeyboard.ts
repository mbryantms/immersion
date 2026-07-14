import { useEffect, useRef } from "react";

/** Global player shortcuts; disabled while typing or composing (IME). */
export function useKeyboard(
  handlers: Record<string, (e: KeyboardEvent) => void>,
  alwaysHandleOnControls: string[] = ["Escape"],
) {
  const ref = useRef(handlers);
  const alwaysHandleRef = useRef(alwaysHandleOnControls);
  ref.current = handlers;
  alwaysHandleRef.current = alwaysHandleOnControls;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.isComposing) return;
      const isTextEntry = t.tagName === "INPUT"
        || t.tagName === "TEXTAREA"
        || t.tagName === "SELECT"
        || t.isContentEditable;
      const isControl = t.tagName === "BUTTON" || !!t.closest("[role='button']");
      // Escape remains a global dismissal key even when focus is on a dialog
      // action. Text entry always owns Space; other controls may opt a key into
      // global handling for a deliberate workflow such as "Space to resume".
      if (isTextEntry && e.key !== "Escape") return;
      if (isControl && !alwaysHandleRef.current.includes(e.key)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
