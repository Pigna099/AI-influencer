import { useCallback, useEffect, useState } from "react";
import { api, Character, ExecutionJob, JobEvent } from "../api";
import { formatDuration } from "../lib/format";
import { useI18n } from "../i18n";
import AppHeader from "./ui/AppHeader";
import AsyncBoundary from "./ui/AsyncBoundary";
import EmptyState from "./ui/EmptyState";
import JobProgress from "./ui/JobProgress";
import PageHeader from "./ui/PageHeader";
import CompactToolbar from "./ui/CompactToolbar";
import StatusBadge from "./ui/StatusBadge";

const JOB_TYPES = [
  "training", "video", "image", "identity_run", "lora_validation", "dataset_generate", "dataset_variation",
  "dataset_import", "dataset_classify", "consistency_check", "pose_extract", "avatar",
];
const PAGE = 50;

function jobEta(job: ExecutionJob, t: (key: "jobs.eta", values?: Record<string, string>) => string): string | null {
  const current = job.progress?.current;
  const total = job.progress?.total;
  if (!current || !total || !job.started_at || current <= 0) return null;
  const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
  if (elapsed < 5) return null;
  const remaining = (elapsed * (total - current)) / current;
  return t("jobs.eta", { time: formatDuration(Math.max(1, remaining)) });
}

function progressPercent(job: ExecutionJob) {
  const current = job.progress?.current ?? 0;
  const total = job.progress?.total ?? 0;
  if (!total) return 0;
  return Math.round((current / total) * 100);
}

function JobRow({ job, characterName, busy, onAction }: {
  job: ExecutionJob;
  characterName: string;
  busy: boolean;
  onAction: (job: ExecutionJob, action: "cancel" | "retry") => void;
}) {
  const { t } = useI18n();
  const [events, setEvents] = useState<JobEvent[] | null>(null);
  const loadEvents = () => {
    if (events) return;
    void api.getJobEvents(job.id).then(setEvents).catch(() => setEvents([]));
  };
  const typeLabel = t(`jobs.type.${job.type}` as "jobs.type.training");
  return (
    <article className={`job-item state-${job.state}`}>
      <header>
        <strong>{typeLabel !== `jobs.type.${job.type}` ? typeLabel : job.type}</strong>
        <StatusBadge status={job.state} label={t(`jobs.state.${job.state}` as "jobs.state.queued")} />
        <small>{characterName} · {new Date(job.created_at).toLocaleString()}{job.started_at && job.finished_at ? ` · ${formatDuration((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000)}` : ""}</small>
      </header>
      {job.state === "running" && job.progress?.total ? (
        <div className="job-progress-row">
          <JobProgress percent={progressPercent(job)} label={job.type} />
          <small>{job.progress.current}/{job.progress.total} {job.progress.unit || ""}{jobEta(job, t) ? ` · ${jobEta(job, t)}` : ""}</small>
        </div>
      ) : job.state === "queued" && job.queue_position ? (
        <small className="muted">{t("jobs.queuePosition", { position: job.queue_position })}</small>
      ) : null}
      {job.error_info && (
        <div className={`job-error code-${job.error_info.code}`}>
          <strong>{job.error_info.summary}</strong>
          {job.error_info.remediation && <small>{job.error_info.remediation}</small>}
        </div>
      )}
      <div className="library-actions">
        {(job.state === "running" || job.state === "queued") && <button disabled={busy} onClick={() => onAction(job, "cancel")}>{t("common.cancel")}</button>}
        {(job.state === "failed" || job.state === "canceled") && <button disabled={busy} onClick={() => onAction(job, "retry")}>{t("jobs.retry")}</button>}
        <details className="job-log" onToggle={event => (event.target as HTMLDetailsElement).open && loadEvents()}>
          <summary>{t("jobs.details")}</summary>
          {job.worker && <small>{t("jobs.worker")} {job.worker}{job.gpu != null ? ` · GPU ${job.gpu}` : ""}</small>}
          {job.error_info?.technical_details && <pre>{(job.error_info.technical_details || "").slice(-1200)}</pre>}
          <ul>{events === null ? <li><span className="spinner" /></li> : events.length === 0 ? <li>{t("jobs.noEvents")}</li> : events.map(event => <li key={event.id}><span>{new Date(event.created_at).toLocaleTimeString()}</span> {event.message}</li>)}</ul>
        </details>
      </div>
    </article>
  );
}

export default function JobsPage({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [jobs, setJobs] = useState<ExecutionJob[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [state, setState] = useState("all");
  const [type, setType] = useState("all");
  const [characterId, setCharacterId] = useState("all");
  const [loaded, setLoaded] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reconcileReport, setReconcileReport] = useState<{ orphans: number; removed: number; freed_bytes: number; sample: string[] } | null>(null);
  const [errorsByCode, setErrorsByCode] = useState<{ code: string; count: number }[]>([]);
  const [metrics, setMetrics] = useState<Awaited<ReturnType<typeof api.getMetrics>> | null>(null);
  const [audit, setAudit] = useState<{ id: string; action: string; object_type: string; object_id: string | null; detail: Record<string, unknown>; created_at: string }[]>([]);
  const [alerts, setAlerts] = useState<{ key: string; severity: string; object_type: string; object_id: string | null; title: string; remediation: string }[]>([]);

  const load = useCallback(async (offset = 0) => {
    const data = await api.getJobs({
      state: state === "all" ? undefined : state,
      type: type === "all" ? undefined : type,
      character_id: characterId === "all" ? undefined : characterId,
      limit: PAGE,
      offset,
    });
    setJobs(prev => offset === 0 ? data : [...prev, ...data.filter(job => !prev.some(entry => entry.id === job.id))]);
    setHasMore(data.length === PAGE);
    setLoaded(true);
  }, [state, type, characterId]);

  useEffect(() => { void load(0).catch(e => setError(e instanceof Error ? e.message : String(e))); }, [load]);
  useEffect(() => {
    if (!jobs.some(job => job.state === "running" || job.state === "queued")) return;
    const timer = window.setInterval(() => {
      void load(0).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [jobs, load]);
  useEffect(() => {
    api.getCharacters().then(setCharacters).catch(() => undefined);
    api.getJobSummary().then(summary => setErrorsByCode(summary.errors_by_code ?? [])).catch(() => undefined);
    api.getMetrics().then(setMetrics).catch(() => undefined);
    api.getAudit(15).then(setAudit).catch(() => undefined);
    api.getAlerts().then(data => setAlerts(data.alerts)).catch(() => undefined);
  }, []);

  const reconcile = (deleteOrphans: boolean) => {
    setBusy(true);
    void (async () => {
      try {
        setReconcileReport(await api.reconcileMedia(deleteOrphans));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    })();
  };

  const act = (job: ExecutionJob, action: "cancel" | "retry") => {
    setBusy(true);
    void (async () => {
      try {
        if (action === "cancel") await api.cancelJob(job.id);
        else await api.retryJob(job.id);
        await load(0);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    })();
  };

  const characterName = (job: ExecutionJob) =>
    characters.find(item => item.id === job.character_id)?.name || "—";

  return <div className="playground theme-home">
    <AppHeader current="/jobs" onLogout={onLogout} />
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="home-scroll">
      <section>
        <PageHeader
          eyebrow={t("jobs.title")}
          title={t("jobs.subtitle")}
          aside={<CompactToolbar label={t("jobs.filters")} className="library-toolbar jobs-filters">
            <div className="state-chips" role="group" aria-label={t("jobs.filterState")}>
              {(["all", "active", "failed", "succeeded", "canceled"] as const).map(value => <button
                key={value}
                type="button"
                className={state === value ? "on" : undefined}
                aria-pressed={state === value}
                onClick={() => setState(value)}
              >{value === "all" ? t("jobs.state.all") : t(`jobs.state.${value}` as "jobs.state.failed")}</button>)}
            </div>
            <select value={type} onChange={e => setType(e.target.value)} aria-label={t("jobs.filterType")}>
              <option value="all">{t("jobs.filterType")}</option>
              {JOB_TYPES.map(value => <option key={value} value={value}>{t(`jobs.type.${value}` as "jobs.type.training")}</option>)}
            </select>
            <select value={characterId} onChange={e => setCharacterId(e.target.value)} aria-label={t("jobs.filterCharacter")}>
              <option value="all">{t("jobs.filterCharacter")}</option>
              {characters.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </CompactToolbar>}
        />
        {metrics && <div className="metrics-strip">
          <span><b>{metrics.jobs.by_state.running + metrics.jobs.by_state.queued}</b> {t("jobs.metrics.active")}</span>
          <span><b>{metrics.jobs.by_state.succeeded}</b> {t("jobs.metrics.succeeded")}</span>
          <span><b>{metrics.jobs.by_state.failed}</b> {t("jobs.metrics.failed")}</span>
          {Object.entries(metrics.jobs.avg_run_seconds).slice(0, 4).map(([type, seconds]) => <span key={type}>{t(`jobs.type.${type}` as "jobs.type.training")} ≈ {formatDuration(seconds)}</span>)}
          <span><b>{Math.round(metrics.library.approval_rate * 100)}%</b> {t("jobs.metrics.approval")}</span>
          <span>{t("jobs.metrics.storage", { files: metrics.storage.media_files, gb: (metrics.storage.media_bytes / 1024 ** 3).toFixed(2), free: Math.round(metrics.storage.disk_free_bytes / 1024 ** 3) })}</span>
          {metrics.models.loras_missing_checkpoint > 0 && <span className="warn">⚠ {t("jobs.metrics.missingCheckpoints", { count: metrics.models.loras_missing_checkpoint })}</span>}
          {metrics.backups.last_at && <span>{t("jobs.metrics.backup", { date: new Date(metrics.backups.last_at).toLocaleDateString(), size: (metrics.backups.size_bytes || 0) >= 1024 ** 2 ? `${Math.round((metrics.backups.size_bytes || 0) / 1024 ** 2)} MB` : `${Math.max(1, Math.round((metrics.backups.size_bytes || 0) / 1024))} KB` })}</span>}
        </div>}
        {!!errorsByCode.length && <div className="errors-by-code">
          <small className="muted">{t("jobs.errorsByCode")}</small>
          <ul>{errorsByCode.map(entry => <li key={entry.code} title={entry.code}><span>{t(`jobs.error.${entry.code}` as "jobs.error.checkpoint_missing")}</span><b>{entry.count}</b></li>)}</ul>
        </div>}
        {!!alerts.length && <div className="alerts-list">
          {alerts.slice(0, 8).map(alert => <div className={`alert-row ${alert.severity}`} key={alert.key}>
            <span className={`alert-dot ${alert.severity}`} aria-hidden="true" />
            <div><strong>{alert.title}</strong><small>{alert.remediation} · {alert.object_type}{alert.object_id ? ` ${alert.object_id.slice(0, 8)}` : ""}</small></div>
          </div>)}
        </div>}
        <details className="maintenance-panel">
          <summary>{t("jobs.maintenance")}</summary>
        <div className="maintenance-row">
          <button disabled={busy} onClick={() => reconcile(false)}>{t("jobs.scanOrphans")}</button>
          <details className="danger-zone-inline"><summary>{t("jobs.dangerZone")}</summary>
            <button className="danger" disabled={busy} onClick={() => { if (window.confirm(t("jobs.purgeTrashConfirm"))) { setBusy(true); void api.purgeTrash(30).then(result => setReconcileReport({ orphans: 0, removed: result.purged, freed_bytes: 0, sample: [] })).catch(e => setError(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false)); } }}>{t("jobs.purgeTrash")}</button>
          </details>
          {reconcileReport && (reconcileReport.orphans > 0
            ? <span>{t("jobs.orphansFound", { count: reconcileReport.orphans })} <button disabled={busy} className="danger" onClick={() => reconcile(true)}>{t("jobs.deleteOrphans")}</button></span>
            : <span>{reconcileReport.removed > 0 ? t("jobs.orphansRemoved", { count: reconcileReport.removed, gb: (reconcileReport.freed_bytes / 1024 ** 3).toFixed(2) }) : t("jobs.noOrphans")}</span>)}
        </div>
        </details>
        {metrics && <details className="metrics-detail">
          <summary>{t("jobs.metrics.details")}</summary>
          <div className="metrics-grid">
            <section>
              <h3>{t("jobs.metrics.byType")}</h3>
              <table>
                <thead><tr><th>{t("jobs.filterType")}</th><th>✓</th><th>✕</th><th>⨯</th><th>{t("jobs.metrics.avgRun")}</th><th>{t("jobs.metrics.avgQueue")}</th></tr></thead>
                <tbody>
                  {Object.entries(metrics.jobs.by_type).map(([type, states]) => <tr key={type}>
                    <td>{t(`jobs.type.${type}` as "jobs.type.training")}</td>
                    <td>{states.succeeded ?? 0}</td>
                    <td>{states.failed ?? 0}</td>
                    <td>{states.canceled ?? 0}</td>
                    <td>{metrics.jobs.avg_run_seconds[type] != null ? formatDuration(metrics.jobs.avg_run_seconds[type]) : "—"}</td>
                    <td>{metrics.jobs.avg_queue_seconds[type] != null ? formatDuration(metrics.jobs.avg_queue_seconds[type]) : "—"}</td>
                  </tr>)}
                </tbody>
              </table>
            </section>
            <section>
              <h3>{t("jobs.metrics.assets")}</h3>
              <ul className="metrics-list">
                <li><span>{t("jobs.metrics.libraryLine")}</span><b>{metrics.library.approved}/{metrics.library.total}</b></li>
                <li><span>{t("jobs.metrics.trashedLine")}</span><b>{metrics.library.trashed}</b></li>
                <li><span>{t("jobs.metrics.videosLine")}</span><b>{metrics.videos.approved}/{metrics.videos.total}</b></li>
                <li><span>{t("jobs.metrics.datasetsLine")}</span><b>{metrics.datasets.selected_items}</b></li>
                <li><span>{t("jobs.metrics.identityLine")}</span><b>{metrics.identity.frozen}/{metrics.identity.runs}</b></li>
                <li><span>{t("jobs.metrics.charactersLine")}</span><b>{metrics.characters.with_ready_lora}/{metrics.characters.total}</b></li>
              </ul>
            </section>
          </div>
        </details>}
        {!!audit.length && <details className="audit-log">
          <summary>{t("jobs.audit")}</summary>
          <ul>{audit.map(event => <li key={event.id}>
            <span>{new Date(event.created_at).toLocaleString()}</span>
            <code>{event.action}</code>
            <span>{event.object_type}{event.object_id ? ` ${event.object_id.slice(0, 8)}` : ""}{typeof event.detail?.count === "number" ? ` · ${event.detail.count}` : ""}</span>
          </li>)}</ul>
        </details>}
        <AsyncBoundary
          loading={!loaded}
          empty={!jobs.length}
          loadingText={t("common.loadingData")}
          emptyState={<EmptyState symbol="☰" title={t("jobs.empty")} />}
        >
          <div className="job-list jobs-page-list">
            {jobs.map(job => <JobRow key={job.id} job={job} characterName={characterName(job)} busy={busy} onAction={act} />)}
          </div>
          {hasMore && <div className="load-more"><button disabled={busy} onClick={() => void load(jobs.length)}>{t("common.loadMore")}</button></div>}
        </AsyncBoundary>
      </section>
    </div>
  </div>;
}
