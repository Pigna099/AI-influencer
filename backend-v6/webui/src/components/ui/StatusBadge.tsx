const TONES: Record<string, string> = {
  ready: "ok", approved: "ok", succeeded: "ok", active: "ok", completed: "ok",
  running: "busy", queued: "busy", pending: "busy", importing: "busy", classifying: "busy", building: "busy",
  draft: "neutral", canceled: "neutral", archived: "neutral",
  failed: "bad", rejected: "bad", blocked: "bad",
};

export default function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = TONES[status] ?? "neutral";
  return <span className={`status-badge ${tone}`} data-status={status}>{label || status}</span>;
}
