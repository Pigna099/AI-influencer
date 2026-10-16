interface Props {
  label: string;
  completed: number;
  pending: number;
  failed: number;
  total: number;
  showCounts?: boolean;
}

export default function ProgressSummary({ label, completed, pending, failed, total, showCounts = true }: Props) {
  const done = completed + failed;
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="progress-summary">
      <div className="job-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label={label}>
        <i style={{ width: `${percent}%` }} />
      </div>
      <small>{label}</small>
      {showCounts && <div className="progress-counts">
        <span className="ok">✓ {completed}</span>
        {pending > 0 && <span className="busy">◷ {pending}</span>}
        {failed > 0 && <span className="bad">✕ {failed}</span>}
        <span>{percent}%</span>
      </div>}
    </div>
  );
}
