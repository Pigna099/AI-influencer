import { useCallback, useEffect, useState } from "react";
import { api, Character, LibraryImage, VideoClip } from "../api";
import {useI18n} from "../i18n";
import AppHeader from "./ui/AppHeader";
import AsyncBoundary from "./ui/AsyncBoundary";

function VideoCard({ item, sourceImage, busy, onDelete, onError }: {
  item: VideoClip;
  sourceImage: LibraryImage | undefined;
  busy: boolean;
  onDelete: (item: VideoClip) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [poster, setPoster] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    const endpoint = item.thumb_filename
      ? `/api/videos/${item.id}/thumb`
      : sourceImage
        ? `/api/library/${sourceImage.id}/file?v=${encodeURIComponent(sourceImage.filename)}`
        : "";
    if (!endpoint) {
      setPoster("");
      return;
    }
    api.fetchBlob(endpoint)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setPoster(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.id, item.thumb_filename, sourceImage?.id, sourceImage?.filename]);

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  const play = async () => {
    if (url || loading) return;
    setLoading(true);
    try {
      const blob = await api.fetchBlob(`/api/videos/${item.id}/file`);
      setUrl(URL.createObjectURL(blob));
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const seconds = Number(item.params?.seconds || 0);
  const length = Number(item.params?.length || 0);
  return <article className="video-card">
    <div className="video-thumb">
      {url ? <video src={url} controls autoPlay playsInline /> : <>
        {poster ? <img src={poster} alt={item.prompt} loading="lazy" /> : <div className="library-loading"><span>▶</span></div>}
        <button type="button" className="video-play" disabled={loading} onClick={play} aria-label={t("vd.play")}>{loading ? <span className="spinner" /> : "▶"}</button>
      </>}
    </div>
    <div className="video-meta">
      <p>{item.prompt}</p>
      <small>{length ? t("vd.frames", { count: length }) : ""}{length ? ` · ${t("vd.clip", { seconds: (length / (String(item.params?.model || "").includes("wan") ? 16 : 24)).toFixed(1) })}` : ""}{seconds ? ` · gen ${seconds}s` : ""} · seed {item.seed}</small>
      <div className="library-actions"><button className="danger" disabled={busy} onClick={() => onDelete(item)}>{t("common.delete")}</button></div>
    </div>
  </article>;
}

function SourcePreview({ image }: { image: LibraryImage | undefined }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    if (!image) return;
    api.fetchBlob(`/api/library/${image.id}/file?v=${encodeURIComponent(image.filename)}`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image?.id, image?.filename]);
  if (!image) return null;
  return <div className="source-preview">{url ? <img src={url} alt={image.filename} /> : <span className="spinner" />}</div>;
}

export default function VideoPlayground({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [videos, setVideos] = useState<VideoClip[]>([]);
  const [library, setLibrary] = useState<LibraryImage[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [videosHasMore, setVideosHasMore] = useState(false);
  const VIDEOS_PAGE = 50;
  const [mode, setMode] = useState<"image" | "text">("image");
  const [model, setModel] = useState<"wan" | "ltx-distilled" | "ltx-dev" | "hunyuan">("wan");
  const [allLoras, setAllLoras] = useState<{ name: string; family: string }[]>([]);
  const [loraSel, setLoraSel] = useState<Record<string, number>>({});
  const [resolution, setResolution] = useState("832x480");
  const [length, setLength] = useState(81);
  const [steps, setSteps] = useState(4);
  const [seed, setSeed] = useState("");

  const load = useCallback(async (id: string) => {
    if (!id) { setVideos([]); setLibrary([]); setLoaded(true); return; }
    try {
      const [clips, images] = await Promise.all([api.getVideos(id, { limit: VIDEOS_PAGE }), api.getLibrary(id, { limit: 200, status: "approved" })]);
      setVideos(clips);
      setVideosHasMore(clips.length === VIDEOS_PAGE);
      setLibrary(images);
      setSourceId(prev => prev && images.some(image => image.id === prev) ? prev : (images[0]?.id || ""));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    api.getDefaults()
      .then(defaults => {
        const families = ["wan", "ltx-distilled", "ltx-dev", "hunyuan"] as const;
        if (families.includes(defaults.video_model)) setModel(defaults.video_model);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    api.getCharacters()
      .then(items => {
        setCharacters(items);
        if (items.length) setCharacterId(current => current || items[0].id);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => { void load(characterId).catch(() => undefined); }, [characterId, load]);

  useEffect(() => {
    api.getLoras()
      .then(({ loras, families }) => setAllLoras(loras.map(name => ({ name, family: families[name] || "" }))))
      .catch(() => undefined);
  }, []);

  const family = model === "wan" ? "wan" : model === "hunyuan" ? "hunyuan" : "ltx";
  const videoLoras = allLoras
    .filter(entry => entry.family === family)
    .filter(entry => !(family === "wan" && /lightx2v|distilled-lora/i.test(entry.name)))
    .filter(entry => !(family === "ltx" && /distilled-lora/i.test(entry.name)))
    .map(entry => entry.name);
  const presets: Record<string, { resolution: string; resolutionOptions: string[]; length: number; lengthOptions: number[]; steps: number; stepOptions: number[] }> = {
    wan: { resolution: "832x480", resolutionOptions: ["832x480", "1280x720"], length: 81, lengthOptions: [49, 81, 121], steps: 4, stepOptions: [4, 8] },
    ltx: { resolution: "768x512", resolutionOptions: ["768x512", "512x768", "1216x832"], length: 97, lengthOptions: [49, 97, 121], steps: 5, stepOptions: [5, 8] },
    hunyuan: { resolution: "832x480", resolutionOptions: ["832x480", "480x832"], length: 49, lengthOptions: [49, 81, 121], steps: 8, stepOptions: [8, 20] },
  };
  const resolutionOptions = presets[family].resolutionOptions;
  const lengthOptions = presets[family].lengthOptions;
  const stepOptions = presets[family].stepOptions;

  useEffect(() => {
    setResolution(presets[family].resolution);
    setLength(presets[family].length);
    setSteps(presets[family].steps);
    setLoraSel({});
  }, [family]);

  const loadMoreVideos = () => {
    if (!characterId) return;
    void (async () => {
      const clips = await api.getVideos(characterId, { limit: VIDEOS_PAGE, offset: videos.length });
      setVideos(prev => [...prev, ...clips.filter(clip => !prev.some(entry => entry.id === clip.id))]);
      setVideosHasMore(clips.length === VIDEOS_PAGE);
    })();
  };

  const generate = () => {
    if (!characterId || !prompt.trim() || (mode === "image" && !sourceId)) return;
    const [width, height] = resolution.split("x").map(Number);
    setBusy(t("vd.generating"));
    setError("");
    void (async () => {
      try {
        await api.generateVideo(characterId, {
          prompt: prompt.trim(),
          negative: negative.trim() || undefined,
          mode,
          model,
          image_id: mode === "image" ? sourceId : undefined,
          loras: Object.entries(loraSel).map(([name, weight]) => ({ name, weight })),
          width,
          height,
          length,
          steps,
          seed: seed.trim() ? Number(seed) : undefined,
        });
        setVideos(await api.getVideos(characterId));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy("");
      }
    })();
  };

  const removeVideo = (item: VideoClip) => {
    if (!window.confirm(t("vd.deleteConfirm"))) return;
    void (async () => {
      try {
        await api.deleteVideo(item.id);
        setVideos(prev => prev.filter(entry => entry.id !== item.id));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  };

  return <div className="playground theme-images">
    <AppHeader current="/video" onLogout={onLogout} busy={!!busy} />
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="workspace image-workspace" style={{ gridTemplateColumns: "225px minmax(320px, 1fr) 380px" }}>
      <aside className="character-rail">
        <div className="section-title"><h2>{t("ip.characters")}</h2><span>{characters.length}</span></div>
        <div className="rail-list">{characters.map(item => <button key={item.id} className={item.id === characterId ? "selected" : ""} disabled={!!busy} onClick={() => setCharacterId(item.id)}>{item.name}</button>)}</div>
        {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">{characterId ? t("vd.subtitle") : t("ip.title")}</span><h2>{characters.find(item => item.id === characterId)?.name || t("vd.selectCharacter")}</h2><p>{t("vd.subtitle")}</p></div>
          <span className="library-count">{t("vd.count", { count: videos.length })}</span>
        </div>
        <div className="library-scroll">
          <AsyncBoundary
            loading={!loaded}
            empty={!videos.length}
            skeleton="grid"
            loadingText={t("common.loadingData")}
            emptyState={<div className="empty-memory"><span>▶</span><p>{t("vd.empty")}</p></div>}
          >
          <div className="video-grid">{videos.map(item => <VideoCard key={item.id} item={item} sourceImage={library.find(image => image.id === item.source_image_id)} busy={!!busy} onDelete={removeVideo} onError={setError} />)}</div>
          {videosHasMore && <div className="load-more"><button disabled={!!busy} onClick={loadMoreVideos}>{t("common.loadMore")}</button></div>}
          </AsyncBoundary>
        </div>
      </main>
      <aside className="inspector image-inspector">
        <div className="section-title"><h2>{t("vd.generatePanel")}</h2></div>
        {busy && <p className="memory-status" role="status"><span className="spinner" />{busy} <button className="text-button danger" onClick={() => void api.interruptGeneration()}>{t("common.cancel")}</button></p>}
        <div className="ip-form">
          <label>{t("vd.mode")}<select value={mode} disabled={!!busy} onChange={e => setMode(e.target.value as "image" | "text")}><option value="image">{t("vd.modeImage")}</option><option value="text">{t("vd.modeText")}</option></select></label>
          {mode === "image" && <label>{t("vd.source")}<select value={sourceId} disabled={!!busy || !library.length} onChange={e => setSourceId(e.target.value)}>
            {!library.length && <option value="">{loaded ? t("vd.noApproved") : t("common.loadingData")}</option>}
            {library.map(image => <option key={image.id} value={image.id}>{(image.caption || image.prompt || image.filename).slice(0, 70)}</option>)}
          </select></label>}
          {mode === "image" && <SourcePreview image={library.find(image => image.id === sourceId)} />}
          <label>{t("vd.prompt")}<textarea rows={3} value={prompt} disabled={!!busy} onChange={e => setPrompt(e.target.value)} placeholder={t("vd.promptPlaceholder")} maxLength={2000} /></label>
          <details>
            <summary>{t("ip.details")}</summary>
            <label>{t("vd.negative")}<textarea rows={2} value={negative} disabled={!!busy} onChange={e => setNegative(e.target.value)} maxLength={2000} /></label>
            <label>{t("vd.resolution")}<select value={resolution} disabled={!!busy} onChange={e => setResolution(e.target.value)}>{resolutionOptions.map(option => <option key={option} value={option}>{option.replace("x", "×")}</option>)}</select></label>
            <label>{t("vd.length")}<select value={length} disabled={!!busy} onChange={e => setLength(Number(e.target.value))}>{lengthOptions.map(option => <option key={option} value={option}>{t("vd.frames", { count: option })}</option>)}</select></label>
            <label>{t("vd.steps")}<select value={steps} disabled={!!busy} onChange={e => setSteps(Number(e.target.value))}>{stepOptions.map(option => <option key={option} value={option}>{option}</option>)}</select></label>
            <label>{t("vd.seed")}<input value={seed} disabled={!!busy} onChange={e => setSeed(e.target.value)} inputMode="numeric" placeholder="random" /></label>
            <label>{t("vd.model")}<select value={model} disabled={!!busy} onChange={e => setModel(e.target.value as "wan" | "ltx-distilled" | "ltx-dev" | "hunyuan")}><option value="wan">{t("vd.modelWan")}</option><option value="ltx-distilled">{t("vd.modelLtxDistilled")}</option><option value="ltx-dev">{t("vd.modelLtxDev")}</option><option value="hunyuan">{t("vd.modelHunyuan")}</option></select></label>
            <div className="lora-video">
              <span>{t("vd.loras")}</span>
              {!videoLoras.length && <small className="muted">{t("vd.lorasNone")}</small>}
              {videoLoras.map(name => <label className="lora-video-row" key={name}>
                <input type="checkbox" disabled={!!busy} checked={name in loraSel} onChange={e => setLoraSel(prev => {
                  const next = { ...prev };
                  if (e.target.checked) next[name] = prev[name] ?? 1; else delete next[name];
                  return next;
                })} />
                <span title={name}>{name.replace(".safetensors", "")}</span>
                {name in loraSel && <input className="lora-weight" type="number" min={0} max={2} step={0.05} value={loraSel[name]} disabled={!!busy} onChange={e => setLoraSel(prev => ({ ...prev, [name]: Number(e.target.value) }))} />}
              </label>)}
            </div>
          </details>
          <button className="primary" disabled={!!busy || !characterId || !prompt.trim() || (mode === "image" && !sourceId)} onClick={generate}>{t("vd.generate")}</button>
          {!busy && !characterId && <small className="hint">{t("hint.selectCharacter")}</small>}
          {!busy && characterId && mode === "image" && !library.length && loaded && <small className="hint">{t("vd.noApproved")}</small>}
          {!busy && characterId && mode === "image" && !!library.length && !sourceId && <small className="hint">{t("hint.selectSource")}</small>}
          {!busy && characterId && !prompt.trim() && <small className="hint">{t("hint.enterPrompt")}</small>}
        </div>
      </aside>
    </div>
  </div>;
}
