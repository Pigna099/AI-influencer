import { ReactNode, useEffect, useId, useRef } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  summary?: string;
  closeLabel: string;
  size?: "default" | "wide";
  footer?: ReactNode;
  children: ReactNode;
}

export default function InspectorDrawer({ open, onClose, title, summary, closeLabel, size = "default", footer, children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    triggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!panel.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handler);
    panelRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = previousOverflow;
      const trigger = triggerRef.current;
      if (trigger) window.setTimeout(() => trigger.focus(), 0);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="inspector-drawer-backdrop" onClick={onClose}>
      <div
        ref={panelRef}
        className={`inspector-drawer${size === "wide" ? " size-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={event => event.stopPropagation()}
      >
        <header>
          <div>
            <strong id={titleId}>{title}</strong>
            {summary && <small className="muted">{summary}</small>}
          </div>
          <button type="button" onClick={onClose} aria-label={closeLabel}>×</button>
        </header>
        <div className="inspector-drawer-body">{children}</div>
        {footer && <footer className="inspector-drawer-footer">{footer}</footer>}
      </div>
    </div>
  );
}
