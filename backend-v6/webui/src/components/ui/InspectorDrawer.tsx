import { ReactNode, useEffect, useRef } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  summary?: string;
  closeLabel: string;
  children: ReactNode;
}

export default function InspectorDrawer({ open, onClose, title, summary, closeLabel, children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="inspector-drawer-backdrop" onClick={onClose}>
      <div
        ref={panelRef}
        className="inspector-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={event => event.stopPropagation()}
      >
        <header>
          <div>
            <strong>{title}</strong>
            {summary && <small className="muted">{summary}</small>}
          </div>
          <button type="button" onClick={onClose} aria-label={closeLabel}>×</button>
        </header>
        <div className="inspector-drawer-body">{children}</div>
      </div>
    </div>
  );
}
