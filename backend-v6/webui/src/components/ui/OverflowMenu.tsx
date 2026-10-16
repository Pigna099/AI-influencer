import { ReactNode } from "react";

export default function OverflowMenu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="overflow-menu">
      <summary aria-label={label} title={label}><span aria-hidden="true">⋯</span></summary>
      <div>{children}</div>
    </details>
  );
}
