import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ExecutionJob } from "../../api";
import { useI18n } from "../../i18n";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { formatDuration } from "../../lib/format";
import InspectorDrawer from "./InspectorDrawer";
import JobProgress from "./JobProgress";
import StatusBadge from "./StatusBadge";

interface Summary {
  active: ExecutionJob[];
  failed: ExecutionJob[];
  active_count: number;
  failed_count: number;
}

const MAX_ACTIVE = 5;
const MAX_FAILED = 3;

export default function JobTray() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const isNarrow = useMediaQuery("(max-width: 639px)");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [open, setOpen] = useState(false);
  const [names, setNames] = useState<{ characters: Record<string, string>; sources: Record<string, string> }>({ characters: {}, sources: {} });
  const [announcement, setAnnouncement] = useState("");
  const previousFailed = useRef<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const tick = useCallback(() => {
    if (document.visibilityState !== "visible") return;
    api.getJobSummary()
      .then(data => {
        setSummary(data);
        if (previousFailed.current !== null && data.failed_count > previousFailed.current) {
          setAnnouncement(t("jobs.trayAttention", { count: data.failed_count }));
        }
        previousFailed.current = data.failed_count;
      })
      .catch(() => undefined);
  }, [t]);

  useEffect(() => {
    tick();
    const timer = window.setInterval(tick, 5000);
    const onVisible = () => tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [tick]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    Promise.all([api.getCharacters(), api.getDatasetSources()])
      .then(([characters, sources]) => {
        if (!live) return;
        setNames({
          characters: Object.fromEntries(characters.map(item => [item.id, item.name])),
          sources: Object.fromEntries(sources.map(item => [item.id, item.name])),
        });
      })
      .catch(() => undefined);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    const onOutside = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onOutside);
    return () => {
      live = false;
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onOutside);
    };
  }, [open]);

  const close = () => {
    setOpen(false);
    window.setTimeout(() => buttonRef.current?.focus(), 0);
  };

  const activeCount = summary?.active_count ?? 0;
  const failedCount = summary?.failed_count ?? 0;
  if (!activeCount && !failedCount) return null;

  const label = failedCount
    ? t("jobs.trayAriaBoth", { active: activeCount, failed: failedCount })
    : t("jobs.trayRunning", { count: activeCount });

  const contextName = (job: ExecutionJob): string | null => {
    if (job.character_id && names.characters[job.character_id]) return names.characters[job.character_id];
    if (job.external_id && names.sources[job.external_id]) return names.sources[job.external_id];
    return null;
  };

  const eta = (job: ExecutionJob): string => {
    if (job.state === "queued") {
      return job.queue_position ? t("jobs.queuePosition", { position: job.queue_position }) : t("jobs.trayQueued");
    }
    const current = job.progress?.current ?? 0;
    const total = job.progress?.total ?? 0;
    if (!current || !total || !job.started_at) return t("jobs.etaEstimating");
    const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
    if (elapsed < 10) return t("jobs.etaEstimating");
    return t("jobs.eta", { time: formatDuration(Math.max(1, (elapsed * (total - current)) / current)) });
  };

  const openJob = (job: ExecutionJob) => {
    setOpen(false);
    navigate(`/jobs?type=${encodeURIComponent(job.type)}&job=${encodeURIComponent(job.id)}`);
  };

  const row = (job: ExecutionJob, withError: boolean) => {
    const current = job.progress?.current ?? 0;
    const total = job.progress?.total ?? 0;
    const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const name = contextName(job);
    return (
      <button key={job.id} type="button" className="job-tray-row" onClick={() => openJob(job)}>
        <span className="job-tray-row-head">
          <strong>{t(`jobs.type.${job.type}` as "jobs.type.training")}</strong>
          {name && <small>{name}</small>}
          <StatusBadge status={job.state} label={t(`jobs.state.${job.state}` as "jobs.state.queued")} />
        </span>
        {job.state === "running" && total > 0 && <JobProgress percent={percent} label={`${current}/${total}${job.progress?.unit ? ` ${job.progress.unit}` : ""}`} />}
        <span className="job-tray-row-meta">
          {job.state === "running" && total > 0 && <small>{current}/{total}{job.progress?.unit ? ` ${job.progress.unit}` : ""}</small>}
          {(job.state === "running" || job.state === "queued") && <small>{eta(job)}</small>}
          {withError && job.finished_at && <small>{new Date(job.finished_at).toLocaleString()}</small>}
        </span>
        {withError && job.error_info && <small className="job-tray-error">{job.error_info.summary}</small>}
      </button>
    );
  };

  const content = (
    <div className="job-tray-content">
      <div className="job-tray-head">
        <strong>{t("jobs.title")}</strong>
        <span className="muted">{t("jobs.trayHeadCounts", { active: activeCount, failed: failedCount })}</span>
      </div>
      {summary?.active.length ? (
        <div className="job-tray-section">
          <small className="eyebrow">{t("jobs.trayActiveSection")}</small>
          {summary.active.slice(0, MAX_ACTIVE).map(job => row(job, false))}
          {summary.active.length > MAX_ACTIVE && <small className="muted">{t("jobs.trayMoreActive", { count: summary.active.length - MAX_ACTIVE })}</small>}
        </div>
      ) : (
        <p className="muted">{t("jobs.trayEmpty")}</p>
      )}
      {!!summary?.failed.length && (
        <div className="job-tray-section">
          <small className="eyebrow">{t("jobs.trayRecentFailures")}</small>
          {summary.failed.slice(0, MAX_FAILED).map(job => row(job, true))}
        </div>
      )}
      <div className="job-tray-foot">
        <Link className="primary" to="/jobs" onClick={() => setOpen(false)}>{t("jobs.viewAll")}</Link>
      </div>
    </div>
  );

  return (
    <div className="job-tray-wrap" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="job-tray"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => setOpen(value => !value)}
      >
        {activeCount > 0 && <span className="job-tray-active"><span className="spinner" />{activeCount}</span>}
        {failedCount > 0 && <span className="job-tray-failed">{failedCount}</span>}
      </button>
      {open && (isNarrow
        ? <InspectorDrawer open onClose={close} title={t("jobs.title")} closeLabel={t("common.close")}>{content}</InspectorDrawer>
        : <div className="job-tray-popover" role="dialog" aria-label={t("jobs.trayTitle")}>{content}</div>)}
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
    </div>
  );
}
