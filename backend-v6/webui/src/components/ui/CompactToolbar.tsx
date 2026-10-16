import { ReactNode } from "react";

export default function CompactToolbar({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return <div className={`compact-toolbar ${className || ""}`.trim()} role="toolbar" aria-label={label}>{children}</div>;
}
