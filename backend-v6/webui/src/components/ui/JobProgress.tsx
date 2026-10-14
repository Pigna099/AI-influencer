export default function JobProgress({ percent, label }: { percent: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="job-bar" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <i style={{ width: `${clamped}%` }} />
    </div>
  );
}
