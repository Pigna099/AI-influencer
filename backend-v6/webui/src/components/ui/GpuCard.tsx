import { GpuStatus } from "../../api";
import { useI18n } from "../../i18n";

type Role = "media" | "text" | "off";

function tone(value: number): "ok" | "warn" | "bad" {
  if (value >= 85) return "bad";
  if (value >= 60) return "warn";
  return "ok";
}

const TONE_COLOR: Record<string, string> = { ok: "#59c6c6", warn: "#e0b25f", bad: "#e0736f" };

function Gauge({ value, label }: { value: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const length = Math.PI * 40;
  const filled = (clamped / 100) * length;
  return (
    <svg viewBox="0 0 100 64" className="gpu-gauge" role="img" aria-label={`${label} ${clamped}%`}>
      <path d="M 10 52 A 40 40 0 0 1 90 52" fill="none" stroke="#1d2a40" strokeWidth="9" strokeLinecap="round" />
      <path
        d="M 10 52 A 40 40 0 0 1 90 52"
        fill="none"
        stroke={TONE_COLOR[tone(clamped)]}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${length}`}
      />
      <text x="50" y="50" textAnchor="middle" className="gpu-gauge-value">{clamped}%</text>
    </svg>
  );
}

function gb(value: number) {
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

export default function GpuCard({ gpu, role, busy, onRole }: {
  gpu: GpuStatus | { index: number };
  role: Role;
  busy: boolean;
  onRole: (role: Role) => void;
}) {
  const { t } = useI18n();
  const live = "memory_total" in gpu;
  const shortName = live ? gpu.name.replace("NVIDIA GeForce ", "") : t("home.gpu.noData");
  const memoryPercent = live && gpu.memory_total ? Math.min(100, (gpu.memory_used / gpu.memory_total) * 100) : 0;
  const powerPercent = live && gpu.power_watts != null && gpu.power_limit
    ? Math.min(100, (gpu.power_watts / gpu.power_limit) * 100)
    : 0;
  const powerLabel = live && gpu.power_watts != null
    ? (gpu.power_limit ? `${Math.round(gpu.power_watts)} / ${Math.round(gpu.power_limit)} W` : `${Math.round(gpu.power_watts)} W`)
    : "";
  const roles: Role[] = ["media", "text", "off"];
  const roleLabel: Record<Role, string> = {
    media: t("home.plan.media"),
    text: t("home.plan.text"),
    off: t("home.plan.off"),
  };
  return (
    <article className="gpu-card">
      <div className="gpu-card-main">
        {live ? <Gauge value={gpu.utilization} label={`GPU ${gpu.index}`} /> : <div className="gpu-gauge gpu-gauge-placeholder" aria-hidden="true" />}
        <div className="gpu-card-side">
          <header>
            <strong>GPU {gpu.index} · {shortName}</strong>
            {live && gpu.temperature != null && <span className="gpu-temp">{gpu.temperature}°C</span>}
          </header>
          <div className="gpu-role" role="group" aria-label={`${t("home.plan.role")} GPU ${gpu.index}`}>
            {roles.map(value => (
              <button
                key={value}
                type="button"
                disabled={busy}
                className={role === value ? "selected" : undefined}
                aria-pressed={role === value}
                onClick={() => onRole(value)}
              >
                {roleLabel[value]}
              </button>
            ))}
          </div>
          {live && (
            <>
              <div className={`gpu-bar tone-${tone(memoryPercent)}`} title={`${gb(gpu.memory_used)} / ${gb(gpu.memory_total)}`}>
                <i style={{ width: `${memoryPercent}%` }} />
                <span className="gpu-bar-label">{gb(gpu.memory_used)} / {gb(gpu.memory_total)}</span>
              </div>
              {gpu.power_watts != null && (
                <div className={`gpu-bar tone-${tone(powerPercent)}`} title={powerLabel}>
                  <i style={{ width: `${powerPercent}%` }} />
                  <span className="gpu-bar-label">{powerLabel}</span>
                </div>
              )}
              <small>{gpu.memory_utilization}% {t("home.gpu.mem")}</small>
            </>
          )}
        </div>
      </div>
      {live && !!gpu.processes.length && (
        <details className="gpu-processes">
          <summary>{t("home.gpu.processes", { count: gpu.processes.length })}</summary>
          <ul>{gpu.processes.map(process => (
            <li key={`${gpu.index}-${process.pid}-${process.name}`}>
              <span title={process.name}>{process.name}</span>
              <b>{gb(process.vram)}</b>
            </li>
          ))}</ul>
        </details>
      )}
    </article>
  );
}
