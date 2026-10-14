import { ReactNode } from "react";

interface Props {
  title: string;
  summary?: string;
  open?: boolean;
  className?: string;
  children: ReactNode;
}

export default function AdvancedSettings({ title, summary, open, className, children }: Props) {
  return (
    <details className={className} open={open}>
      <summary>{title}{summary && <small className="summary-hint">{summary}</small>}</summary>
      {children}
    </details>
  );
}
