import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, CharacterProfile, DatasetImage, DatasetSource } from "../api";
import { useI18n, LanguageSwitch } from "../i18n";
import Lightbox from "./Lightbox";

const detailFields = ["pose", "setting", "lighting", "scene", "outfit", "body", "skin", "camera", "mood", "art_style"] as const;

function DatasetThumb({ item, onView, select, videoLabel }: { item: DatasetImage; onView: (url: string, alt: string, video?: boolean) => void; select: () => void; videoLabel: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    api.fetchBlob(`/api/dataset/images/${item.id}/thumb`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setUrl(""));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.id]);
  const openMedia = async () => {
    if (item.kind === "video") {
      try {
        const blob = await api.fetchBlob(`/api/dataset/images/${item.id}/file`);
        onView(URL.createObjectURL(blob), item.caption || item.filename, true);
      } catch { /* ignore */ }
      return;
    }
    if (url) onView(url, item.caption || item.filename, false);
  };
  return <div className="dataset-thumb">
    {url ? <img src={url} alt={item.caption || item.filename} loading="lazy" /> : <span className="spinner" />}
    {item.kind === "video" && <span className="badge video">▶ {videoLabel}</span>}
    <span className={`badge ${item.status}`}>{item.status}</span>
    <div className="dataset-thumb-actions">
      <button type="button" disabled={!url} onClick={() => void openMedia()}>⌕</button>
      <button type="button" onClick={select}>≡</button>
    </div>
  </div>;
}

export default function DatasetPlayground({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [sources, setSources] = useState<DatasetSource[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [images, setImages] = useState<DatasetImage[]>([]);
  const [selected, setSelected] = useState<DatasetImage | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"telegram" | "urls" | "folder" | "instagram">("telegram");
  const [reference, setReference] = useState("");
  const [limit, setLimit] = useState(100);
  const [classify, setClassify] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [profileDraft, setProfileDraft] = useState<CharacterProfile | null>(null);
  const [characterName, setCharacterName] = useState("");
  const [viewer, setViewer] = useState<{ url: string; alt: string; video?: boolean } | null>(null);
  const generation = useRef(0);
  const source = sources.find(item => item.id === sourceId) || null;
  const active = source && ["pending", "importing", "classifying"].includes(source.status);

  const loadSources = useCallback(async () => {
    const listing = await api.getDatasetSources();
    setSources(listing);
    return listing;
  }, []);

  const loadImages = useCallback(async (id: string) => {
    if (!id) { setImages([]); return; }
    const epoch = generation.current;
    const items = await api.getDatasetImages(id);
    if (epoch === generation.current) setImages(items);
  }, []);

  useEffect(() => {
    void loadSources().then(listing => {
      if (!sourceId && listing[0]) setSourceId(listing[0].id);
    }).catch(e => setError(e instanceof Error ? e.message : t("common.failed")));
  }, [loadSources, sourceId, t]);

  useEffect(() => {
    generation.current += 1;
    setSelected(null);
    void loadImages(sourceId).catch(() => undefined);
  }, [sourceId, loadImages]);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void loadSources().then(listing => {
        const current = listing.find(item => item.id === sourceId);
        if (current && !["pending", "importing", "classifying"].includes(current.status)) {
          void loadImages(sourceId);
          setBusy(prev => (prev && prev !== t("ds.importing") && prev !== t("ds.classifying") ? prev : ""));
        }
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [active, sourceId, loadSources, loadImages, t]);

  const perform = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError(""); setNotice("");
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : t("common.failed")); } finally { setBusy(""); }
  };

  const createSource = () => {
    if (!name.trim() || !reference.trim()) return;
    void perform(t("ds.importing"), async () => {
      const created = await api.createDatasetSource({ name: name.trim(), kind, reference: reference.trim(), limit, classify });
      await loadSources();
      setSourceId(created.id);
      setName(""); setReference("");
    });
  };

  const classifySource = () => {
    if (!source) return;
    void perform(t("ds.classifying"), async () => {
      const result = await api.classifyDatasetSource(source.id);
      if (!result.started) setError(t("ds.classifyRunning"));
      await loadSources();
    });
  };

  const extractPose = (item: DatasetImage) => {
    void perform(t("ds.poseExtracting"), async () => {
      await api.extractPose({
        source: "dataset",
        source_image_id: item.id,
        name: (item.details?.pose || item.caption || "").slice(0, 80) || undefined,
        tags: item.tags.slice(0, 6),
      });
      setNotice(t("ds.poseExtracted"));
    });
  };

  const exportSource = () => {
    if (!source) return;
    void perform("", async () => {
      const blob = await api.exportDataset(source.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${source.name.replace(/[^\w-]+/g, "_")}.jsonl`;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  };

  const generateProfile = () => {
    if (!source) return;
    void perform(t("ds.profile"), async () => {
      const result = await api.datasetProfile(source.id);
      setProfileDraft(result.profile);
      setCharacterName(source.name);
    });
  };

  const createCharacter = () => {
    if (!profileDraft) return;
    void perform(t("ds.createCharacter"), async () => {
      const created = await api.createCharacter({ name: characterName.trim() || "Dataset", profile: profileDraft });
      setProfileDraft(null);
      setNotice(`${created.name} v${created.version}`);
    });
  };

  const removeSource = (item: DatasetSource) => {
    if (!window.confirm(t("ds.deleteSourceConfirm"))) return;
    void perform("", async () => {
      await api.deleteDatasetSource(item.id);
      const listing = await loadSources();
      if (sourceId === item.id) setSourceId(listing[0]?.id || "");
    });
  };

  const removeImage = (item: DatasetImage) => {
    if (!window.confirm(t("ds.deleteImageConfirm"))) return;
    void perform("", async () => {
      await api.deleteDatasetImage(item.id);
      setImages(prev => prev.filter(entry => entry.id !== item.id));
      if (selected?.id === item.id) setSelected(null);
    });
  };

  return <div className="playground theme-dataset">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v5</b></h1></div>
      <div className="top-actions">
        <nav className="top-nav"><Link to="/">{t("pg.nav.home")}</Link><Link to="/chat">{t("pg.nav.chat")}</Link><Link to="/images">{t("pg.nav.images")}</Link><Link className="selected" to="/dataset">{t("pg.nav.dataset")}</Link><Link to="/loras">{t("pg.nav.loras")}</Link></nav>
        <LanguageSwitch /><button onClick={onLogout} disabled={!!busy}>{t("pg.logout")}</button>
      </div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    {notice && <div className="info-banner" role="status">{notice}<button onClick={() => setNotice("")} aria-label={t("common.close")}>×</button></div>}
    <div className="workspace dataset-workspace">
      <aside className="character-rail">
        <div className="section-title"><h2>{t("ds.newSource")}</h2></div>
        <div className="ip-form">
          <label>{t("ds.name")}<input value={name} disabled={!!busy} onChange={e => setName(e.target.value)} maxLength={120} /></label>
          <label>{t("ds.kind")}<select value={kind} disabled={!!busy} onChange={e => setKind(e.target.value as "telegram" | "urls" | "folder" | "instagram")}><option value="telegram">{t("ds.kind.telegram")}</option><option value="urls">{t("ds.kind.urls")}</option><option value="folder">{t("ds.kind.folder")}</option><option value="instagram">{t("ds.kind.instagram")}</option></select></label>
          <label>{t("ds.reference")}<textarea rows={3} value={reference} disabled={!!busy} onChange={e => setReference(e.target.value)} placeholder={kind === "telegram" ? t("ds.reference.telegram") : kind === "urls" ? t("ds.reference.urls") : kind === "instagram" ? t("ds.reference.instagram") : t("ds.reference.folder")} maxLength={20000} /></label>
          <label>{t("ds.limit")}<input type="number" min="1" max="2000" value={limit} disabled={!!busy} onChange={e => setLimit(Math.max(1, Math.min(2000, Number(e.target.value))))} /></label>
          <label className="auto-label">{t("ds.classify")} <input type="checkbox" checked={classify} disabled={!!busy} onChange={e => setClassify(e.target.checked)} /></label>
          <button className="primary" disabled={!!busy || !name.trim() || !reference.trim()} onClick={createSource}>{t("ds.create")}</button>
        </div>
        <div className="rail-divider" />
        <div className="section-title"><h2>{t("ds.sources")}</h2><span>{sources.length}</span></div>
        <div className="dataset-sources">{sources.map(item => <button key={item.id} className={`dataset-source ${sourceId === item.id ? "selected" : ""}`} disabled={!!busy} onClick={() => setSourceId(item.id)}>
          <strong>{item.name}</strong>
          <small>{item.kind} · {t("ds.mediaCounts", { images: item.images, videos: item.videos })} · {item.status}{item.error ? ` · ${item.error}` : ""}</small>
        </button>)}
          {!sources.length && <p className="muted">{t("ds.noSources")}</p>}
        </div>
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">{t("ds.title")}</span><h2>{source?.name || t("ds.sources")}</h2><p>{t("ds.subtitle")}</p></div>
          {!!images.length && <span className="library-count">{t("ip.imagesCount", { count: images.length })}</span>}
        </div>
        <div className="library-toolbar">
          <button disabled={!!busy || !source} onClick={classifySource}>{t("ds.classifyPending")}</button>
          <button disabled={!!busy || !source} onClick={exportSource}>{t("ds.export")}</button>
          <button disabled={!!busy || !source} onClick={generateProfile}>{t("ds.profile")}</button>
          <button className="danger" disabled={!!busy || !source} onClick={() => source && removeSource(source)}>{t("common.delete")}</button>
          {busy && <span className="memory-status" role="status"><span className="spinner" />{busy}</span>}
        </div>
        <div className="library-scroll">
          {!images.length && <div className="empty-memory"><span>◎</span><p>{t("ds.noSources")}</p></div>}
          <div className="library-grid">{images.map(item => <article className={`library-card status-${item.status === "ready" ? "approved" : item.status === "failed" || item.status === "blocked" ? "rejected" : ""}`} key={item.id}>
            <DatasetThumb item={item} onView={(url, alt, video) => setViewer({ url, alt, video })} select={() => setSelected(item)} videoLabel={t("ds.video")} />
            <div className="library-meta">
              <p>{item.caption || item.filename}</p>
              {!!item.tags.length && <div className="library-tags">{item.tags.slice(0, 8).map(tag => <span key={tag}>{tag}</span>)}</div>}
              <div className="library-actions"><button onClick={() => setSelected(item)}>{t("ds.details")}</button><button className="danger" disabled={!!busy} onClick={() => removeImage(item)}>{t("common.delete")}</button></div>
            </div>
          </article>)}</div>
        </div>
      </main>
      <aside className="inspector dataset-inspector">
        <div className="section-title"><h2>{t("ds.details")}</h2></div>
        {!selected && <p className="muted">{t("ds.noImageSelected")}</p>}
        {selected && <>
          <p className="scope-label">{selected.kind === "video" ? t("ds.video") : t("ds.image")} · {selected.status}{selected.kind === "image" ? ` · ${selected.width}×${selected.height}` : ""}</p>
          <p className="dataset-caption">{selected.kind === "video" ? t("ds.videoNoCaption") : selected.caption}</p>
          <dl className="dataset-details">{detailFields.map(field => <div key={field}><dt>{t(`ds.fields.${field}` as "ds.fields.pose")}</dt><dd>{selected.details?.[field] || "—"}</dd></div>)}</dl>
          {!!selected.tags.length && <div className="library-tags">{selected.tags.map(tag => <span key={tag}>{tag}</span>)}</div>}
          {selected.kind === "image" && <button disabled={!!busy} onClick={() => extractPose(selected)}>{t("ds.poseExtract")}</button>}
          <button className="danger text-button" disabled={!!busy} onClick={() => removeImage(selected)}>{t("common.delete")}</button>
        </>}
      </aside>
    </div>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} video={viewer.video} onClose={() => setViewer(null)} />}
    {profileDraft && <div className="modal-backdrop"><div className="modal fan-editor" role="dialog" aria-modal="true" aria-label={t("ds.profileTitle")}>
      <h2>{t("ds.profileTitle")}</h2>
      <div className="draft-preview">{Object.entries(profileDraft).map(([key, value]) => <div key={key}><strong>{key}</strong><p>{value}</p></div>)}</div>
      <label>{t("ds.characterName")}<input value={characterName} onChange={e => setCharacterName(e.target.value)} maxLength={120} /></label>
      <div className="modal-actions"><button type="button" onClick={() => setProfileDraft(null)} disabled={!!busy}>{t("common.cancel")}</button><button className="primary" disabled={!!busy || !characterName.trim()} onClick={createCharacter}>{t("ds.createCharacter")}</button></div>
    </div></div>}
  </div>;
}
