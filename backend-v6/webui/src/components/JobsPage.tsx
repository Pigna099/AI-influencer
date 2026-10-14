import { useCallback, useEffect, useState } from "react";
import { api, Character, ExecutionJob, JobEvent } from "../api";
import { useI18n } from "../i18n";
import AppHeader from "./ui/AppHeader";
import AsyncBoundary from "./ui/AsyncBoundary";
import EmptyState from "./ui/EmptyState";
import JobProgress from "./ui/JobProgress";
import PageHeader from "./ui/PageHeader";
import StatusBadge from "./ui/StatusBadge";

const JOB_TYPES = [
  "training", "video", "image", "dataset_generate", "dataset_variation",
  "dataset_import", "dataset_classify", "consistency_check", "pose_extract", "avatar",
];
const PAGE = 50;

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
        <small>{characterName} · {new Date(job.created_at).toLocaleString()}</small>
      </header>
      {job.state === "running" && job.progress?.total ? (
        <div className="job-progress-row">
          <JobProgress percent={progressPercent(job)} label={job.type} />
          <small>{job.progress.current}/{job.progress.total} {job.progress.unit || ""}</small>
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
    api.getCharacters().then(setCharacters).catch(() => undefined);
  }, []);

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
          aside={<div className="library-toolbar jobs-filters">
            <select value={state} onChange={e => setState(e.target.value)} aria-label={t("jobs.filterState")}>
              {["all", "active", "queued", "running", "succeeded", "failed", "canceled"].map(value => <option key={value} value={value}>{value === "all" ? t("jobs.filterState") : t(`jobs.state.${value}` as "jobs.state.queued")}</option>)}
            </select>
            <select value={type} onChange={e => setType(e.target.value)} aria-label={t("jobs.filterType")}>
              <option value="all">{t("jobs.filterType")}</option>
              {JOB_TYPES.map(value => <option key={value} value={value}>{t(`jobs.type.${value}` as "jobs.type.training")}</option>)}
            </select>
            <select value={characterId} onChange={e => setCharacterId(e.target.value)} aria-label={t("jobs.filterCharacter")}>
              <option value="all">{t("jobs.filterCharacter")}</option>
              {characters.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>}
        />
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
