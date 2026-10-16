import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useI18n } from "../../i18n";

export default function JobTray() {
  const { t } = useI18n();
  const [active, setActive] = useState(0);
  const [failed, setFailed] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const previousFailed = useRef<number | null>(null);

  useEffect(() => {
    let live = true;
    const tick = () => api.getJobSummary()
      .then(data => {
        if (!live) return;
        setActive(data.active_count);
        setFailed(data.failed_count);
        // Announce only when new failures appear, not on every poll.
        if (previousFailed.current !== null && data.failed_count > previousFailed.current) {
          setAnnouncement(t("jobs.trayAttention", { count: data.failed_count }));
        }
        previousFailed.current = data.failed_count;
      })
      .catch(() => undefined);
    void tick();
    const timer = window.setInterval(tick, 5000);
    return () => { live = false; window.clearInterval(timer); };
  }, []);

  if (!active && !failed) return null;
  const label = failed
    ? t("jobs.trayAttention", { count: failed })
    : t("jobs.trayRunning", { count: active });
  return (
    <Link className="job-tray" to="/jobs" aria-label={label} title={label}>
      {active > 0 && <span className="job-tray-active"><span className="spinner" />{active}</span>}
      {failed > 0 && <span className="job-tray-failed">{failed}</span>}
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
    </Link>
  );
}
