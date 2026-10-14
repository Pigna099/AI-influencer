export default function EmptyState({ symbol, title, hint }: { symbol?: string; title: string; hint?: string }) {
  return (
    <div className="empty-memory">
      {symbol && <span aria-hidden="true">{symbol}</span>}
      <p>{title}</p>
      {hint && <small>{hint}</small>}
    </div>
  );
}
