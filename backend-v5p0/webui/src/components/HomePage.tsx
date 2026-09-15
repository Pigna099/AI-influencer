import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Character, CheckpointInfo, GpuReport, OllamaModel } from "../api";
import { useI18n, LanguageSwitch } from "../i18n";
import CharacterAvatar from "./CharacterAvatar";
import Lightbox from "./Lightbox";

type FlagState = "ok" | "warn" | "down";

interface Flag {
  key: string;
  label: string;
  state: FlagState;
  detail: string;
}

function gb(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export default function HomePage({ onLogout }: { onLogout: () => void }) {
  const { t, lang } = useI18n();
  const [flags, setFlags] = useState<Flag[]>([]);
  const [gpu, setGpu] = useState<GpuReport | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loraCounts, setLoraCounts] = useState<Record<string, number>>({});
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [loras, setLoras] = useState<string[]>([]);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const next: Flag[] = [];

    try {
      await api.getHealth();
      next.push({ key: "api", label: t("home.flag.api"), state: "ok", detail: t("home.flag.apiOk") });
    } catch {
      next.push({ key: "api", label: t("home.flag.api"), state: "down", detail: t("home.flag.apiDown") });
    }

    try {
      const data = await api.getCheckpoints();
      setCheckpoints(data.checkpoints ?? []);
      next.push({
        key: "comfyui",
        label: t("home.flag.comfyui"),
        state: data.available ? "ok" : "down",
        detail: data.available
          ? t("home.flag.comfyuiOk", { count: (data.checkpoints ?? []).filter(item => item.usable).length })
          : t("home.flag.comfyuiDown"),
      });
    } catch {
      setCheckpoints([]);
      next.push({ key: "comfyui", label: t("home.flag.comfyui"), state: "down", detail: t("home.flag.comfyuiDown") });
    }

    try {
      const data = await api.getModels();
      setModels(data.models);
      next.push({
        key: "ollama",
        label: t("home.flag.ollama"),
        state: "ok",
        detail: t("home.flag.ollamaOk", { count: data.models.length }),
      });
    } catch {
      setModels([]);
      next.push({ key: "ollama", label: t("home.flag.ollama"), state: "down", detail: t("home.flag.ollamaDown") });
    }

    try {
      const report = await api.getGpuStatus();
      setGpu(report);
      next.push({
        key: "gpu",
        label: t("home.flag.gpu"),
        state: report.available ? "ok" : "warn",
        detail: report.available
          ? t("home.flag.gpuOk", { count: report.gpus.length })
          : (report.error || t("home.flag.gpuDown")),
      });
    } catch {
      setGpu(null);
      next.push({ key: "gpu", label: t("home.flag.gpu"), state: "warn", detail: t("home.flag.gpuDown") });
    }

    try {
      const jobs = await api.getTrainingJobs({ limit: 20 });
      const running = jobs.filter(job => job.status === "running");
      const queued = jobs.filter(job => job.status === "queued");
      const fresh = running.some(
        job => job.heartbeat_at && Date.now() - new Date(job.heartbeat_at).getTime() < 5 * 60 * 1000,
      );
      next.push({
        key: "trainer",
        label: t("home.flag.trainer"),
        state: running.length ? (fresh ? "ok" : "warn") : queued.length ? "warn" : "ok",
        detail: running.length
          ? (fresh ? t("home.flag.trainerRunning") : t("home.flag.trainerStale"))
          : queued.length
            ? t("home.flag.trainerQueue")
            : t("home.flag.trainerIdle"),
      });
    } catch {
      next.push({ key: "trainer", label: t("home.flag.trainer"), state: "warn", detail: t("home.flag.trainerIdle") });
    }

    try {
      const chars = await api.getCharacters();
      setCharacters(chars);
      const counts = await Promise.all(
        chars.slice(0, 20).map(async item => {
          try {
            const items = await api.getCharacterLoras(item.id);
            return [item.id, items.length] as const;
          } catch {
            return [item.id, 0] as const;
          }
        }),
      );
      setLoraCounts(Object.fromEntries(counts));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }

    try {
      const data = await api.getLoras();
      setLoras(data.loras ?? []);
    } catch {
      setLoras([]);
    }

    setFlags(next);
    setLoading(false);
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const freeVram = async () => {
    setLoading(true);
    setError("");
    try {
      await api.freeVram();
      setGpu(await api.getGpuStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      api.getGpuStatus().then(setGpu).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  return <div className="playground theme-home">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v5</b></h1></div>
      <div className="top-actions">
        <nav className="top-nav"><Link className="selected" to="/">{t("pg.nav.home")}</Link><Link to="/chat">{t("pg.nav.chat")}</Link><Link to="/images">{t("pg.nav.images")}</Link><Link to="/dataset">{t("pg.nav.dataset")}</Link><Link to="/loras">{t("pg.nav.loras")}</Link></nav>
        <LanguageSwitch /><button onClick={onLogout} disabled={loading}>{t("pg.logout")}</button>
      </div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="home-scroll">
      <section>
        <div className="section-title"><h2>{t("home.status")}</h2><button disabled={loading} onClick={() => void load()}>{t("lp.refresh")}</button></div>
        <div className="flag-grid">{flags.map(flag => <div className={`flag-card ${flag.state}`} key={flag.key}>
          <span className="flag-dot" aria-hidden="true" />
          <div><strong>{flag.label}</strong><small>{flag.detail}</small></div>
        </div>)}</div>
      </section>
      <section>
        <div className="section-title"><h2>{t("home.gpus")}</h2><div className="section-actions">
          <span>{gpu?.gpus.length ?? 0}</span>
          <button disabled={loading} onClick={() => void freeVram()}>{t("pg.gpu.free")}</button>
        </div></div>
        {gpu?.available ? <div className="gpu-list">{gpu.gpus.map(item => <article className="gpu-card" key={item.index}>
          <header><strong>GPU {item.index} · {item.name.replace("NVIDIA GeForce ", "")}</strong><span>{item.temperature != null ? `${item.temperature}°C` : ""}</span></header>
          <div className="gpu-bar" title={`${gb(item.memory_used)} / ${gb(item.memory_total)}`}><i style={{ width: `${Math.min(100, (item.memory_used / item.memory_total) * 100)}%` }} /></div>
          <small>{gb(item.memory_used)} / {gb(item.memory_total)} · {item.utilization}% util{item.power_watts != null ? ` · ${item.power_watts} W` : ""}</small>
          {!!item.processes.length && <ul>{item.processes.map(process => <li key={`${item.index}-${process.pid}-${process.name}`}><span title={process.name}>{process.name}</span><b>{gb(process.vram)}</b></li>)}</ul>}
        </article>)}</div> : <p className="muted">{gpu === null ? t("pg.gpu.loading") : t("pg.gpu.unavailable")}</p>}
      </section>
      <section>
        <div className="section-title"><h2>{t("home.characters")}</h2><span>{characters.length}</span></div>
        {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}
        <div className="home-characters">{characters.map((item, index) => <Link className="home-character" to="/chat" key={item.id}>
          <CharacterAvatar character={item} index={index} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} />
          <div><strong>{item.name}</strong><small>{item.image_style === "anime" ? t("pg.style.anime") : t("pg.style.real")} · {t("home.loraCount", { count: loraCounts[item.id] ?? 0 })}</small></div>
        </Link>)}</div>
      </section>
      <div className="home-columns">
        <section>
          <div className="section-title"><h2>{t("home.checkpoints")}</h2><span>{checkpoints.length}</span></div>
          <ul className="home-list">{checkpoints.map(item => <li key={item.name}><span title={item.name}>{item.name}</span><b>{item.family}{item.usable ? "" : ` · ${t("home.unusable")}`}</b></li>)}</ul>
          <div className="section-title"><h2>{t("home.loras")}</h2><span>{loras.length}</span></div>
          <ul className="home-list">{loras.map(name => <li key={name}><span title={name}>{name}</span></li>)}</ul>
          {!loras.length && <p className="muted">{t("ip.noLoras")}</p>}
        </section>
        <section>
          <div className="section-title"><h2>{t("home.ollama")}</h2><span>{models.length}</span></div>
          <ul className="home-list">{models.map(model => <li key={model.name}><span title={model.name}>{model.name}</span><b>{model.kind || "chat"} · {model.parameter_size || model.quantization || ""}</b></li>)}</ul>
        </section>
      </div>
      <p className="muted">{t("home.updatedAt", { time: new Date().toLocaleTimeString(lang === "it" ? "it-IT" : "en-GB") })}</p>
    </div>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
  </div>;
}
