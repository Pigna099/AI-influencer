import { ReactNode } from "react";

export default function DangerZone({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="danger-zone" aria-label={title}>
      <h3>{title}</h3>
      {hint && <p className="muted">{hint}</p>}
      <div className="danger-zone-actions">{children}</div>
    </section>
  );
}
