import { ReactNode } from "react";

interface Props {
  eyebrow: string;
  title: string;
  subtitle?: string;
  aside?: ReactNode;
}

export default function PageHeader({ eyebrow, title, subtitle, aside }: Props) {
  return (
    <div className="chat-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {aside}
    </div>
  );
}
