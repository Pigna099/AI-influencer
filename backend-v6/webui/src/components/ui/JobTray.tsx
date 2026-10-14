import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useI18n } from "../../i18n";

export default function JobTray() {
  const { t } = useI18n();
  const [active, setActive] = useState(0);
  const [failed, setFailed] = useState(0);

  useEffect(() => {
    let live = true;
    const tick = () => api.getJobSummary()
      .then(data => {
        if (!live) return;
        setActive(data.active_count);
        setFailed(data.failed_count);
      })
      .catch(() => undefined);
    void tick();
    const timer = window.setInterval(tick, 5000);
    return () => { live = false; window.clearInterval(timer); };
  }, []);

  if (!active && !failed) return null;
  return (
    <Link className="job-tray" to="/jobs" aria-label={t("jobs.trayAria")}>
      {active > 0 && <span className="job-tray-active" role="status"><span className="spinner" />{active}</span>}
      {failed > 0 && <span className="job-tray-failed">{failed}</span>}
    </Link>
  );
}
