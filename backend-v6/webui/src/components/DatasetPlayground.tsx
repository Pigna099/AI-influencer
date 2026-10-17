import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { formatDuration } from "../lib/format";
import { api, CharacterProfile, DatasetImage, DatasetSource, ExecutionJob } from "../api";
import {useI18n} from "../i18n";
import AppHeader from "./ui/AppHeader";
import AsyncBoundary from "./ui/AsyncBoundary";
import InspectorDrawer from "./ui/InspectorDrawer";
import OverflowMenu from "./ui/OverflowMenu";
import ProgressSummary from "./ui/ProgressSummary";
import ContextSelector from "./ui/ContextSelector";
import { useMediaQuery } from "../hooks/useMediaQuery";
import PageHeader from "./ui/PageHeader";
import StatusBadge from "./ui/StatusBadge";
import EmptyState from "./ui/EmptyState";
import Lightbox from "./Lightbox";

const detailFields = ["pose", "setting", "lighting", "scene", "outfit", "body", "skin", "camera", "mood", "art_style"] as const;

function DatasetThumb({ item, select, videoLabel }: { item: DatasetImage; select: () => void; videoLabel: string }) {
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
  const name = item.caption || item.filename;
  return <div className="dataset-thumb" onClick={select} role="button" tabIndex={0} aria-label={`${name}, ${item.status}`} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } }}>
    {url ? <img src={url} alt="" loading="lazy" /> : <span className="spinner" />}
    {item.kind === "video" && <span className="badge video">▶ {videoLabel}</span>}
    <StatusBadge status={item.status} />
  </div>;
}

export default function DatasetPlayground({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [sources, setSources] = useState<DatasetSource[]>([]);
  const [sourceId, setSourceId] = useState("");
  const isNarrow = useMediaQuery("(max-width: 1279px)");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [sourceModalOpen, setSourceModalOpen] = useState(false);
  const [imageSearch, setImageSearch] = useState("");
  const [imageStatusFilter, setImageStatusFilter] = useState("");
  const [images, setImages] = useState<DatasetImage[]>([]);
  const [selected, setSelected] = useState<DatasetImage | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"telegram" | "urls" | "folder" | "x" | "nextcloud">("telegram");
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
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const loadMoreImages = () => {
    if (!sourceId) return;
    void perform("", async () => {
      const items = await api.getDatasetImages(sourceId, { limit: IMAGES_PAGE, offset: images.length });
      setImages(prev => [...prev, ...items.filter(item => !prev.some(entry => entry.id === item.id))]);
      setImagesHasMore(items.length === IMAGES_PAGE);
    });
  };

  const source = sources.find(item => item.id === sourceId) || null;
  const [classifyJob, setClassifyJob] = useState<ExecutionJob | null>(null);
  const active = source && ["pending", "importing", "classifying"].includes(source.status);
  const visibleImages = images.filter(item => {
    if (imageStatusFilter && item.status !== imageStatusFilter) return false;
    const query = imageSearch.trim().toLowerCase();
    if (!query) return true;
    return `${item.caption} ${item.filename} ${(item.tags || []).join(" ")}`.toLowerCase().includes(query);
  });

  const loadSources = useCallback(async () => {
    const listing = await api.getDatasetSources();
    setSources(listing);
    setSourcesLoaded(true);
    return listing;
  }, []);

  const [imagesHasMore, setImagesHasMore] = useState(false);
  const IMAGES_PAGE = 100;

  const loadImages = useCallback(async (id: string) => {
    if (!id) { setImages([]); setImagesHasMore(false); return; }
    const epoch = generation.current;
    const items = await api.getDatasetImages(id, { limit: IMAGES_PAGE });
    if (epoch === generation.current) { setImages(items); setImagesHasMore(items.length === IMAGES_PAGE); }
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
    if (!source || source.status !== "classifying") { setClassifyJob(null); return; }
    let live = true;
    const poll = () => {
      void api.getJobs({ type: "dataset_classify", state: "active", external_id: source.id, limit: 1 })
        .then(items => { if (live) setClassifyJob(items[0] || null); })
        .catch(() => undefined);
    };
    poll();
    const timer = window.setInterval(poll, 4000);
    return () => { live = false; window.clearInterval(timer); };
  }, [source?.id, source?.status]);

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

  const openViewer = (item: DatasetImage) => {
    void (async () => {
      try {
        const blob = await api.fetchBlob(`/api/dataset/images/${item.id}/file`);
        setViewer({ url: URL.createObjectURL(blob), alt: item.caption || item.filename, video: item.kind === "video" });
      } catch {
        /* ignore */
      }
    })();
  };

  const detailsContent = (
    <>

        <div className="section-title"><h2>{t("ds.details")}</h2></div>
        {!selected && <p className="muted">{t("ds.noImageSelected")}</p>}
        {selected && <>
          <p className="scope-label">{selected.kind === "video" ? t("ds.video") : t("ds.image")} · {selected.status}{selected.kind === "image" ? ` · ${selected.width}×${selected.height}` : ""}</p>
          <p className="dataset-caption">{selected.kind === "video" ? t("ds.videoNoCaption") : selected.caption}</p>
          <dl className="dataset-details">{detailFields.map(field => <div key={field}><dt>{t(`ds.fields.${field}` as "ds.fields.pose")}</dt><dd title={String(selected.details?.[field] || "")}>{selected.details?.[field] || "—"}</dd></div>)}</dl>
          {!!selected.tags.length && <div className="library-tags">{selected.tags.map(tag => <span key={tag}>{tag}</span>)}</div>}
          {selected.kind === "image" && <button disabled={!!busy} onClick={() => extractPose(selected)}>{t("ds.poseExtract")}</button>}
          <button className="danger text-button" disabled={!!busy} onClick={() => removeImage(selected)}>{t("common.delete")}</button>
        </>}
    </>
  );

  return <div className="playground theme-dataset">
    <AppHeader current="/dataset" onLogout={onLogout} busy={!!busy} />
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    {notice && <div className="info-banner" role="status">{notice}<button onClick={() => setNotice("")} aria-label={t("common.close")}>×</button></div>}
    <div className="workspace dataset-workspace">
      <aside className="character-rail">
        <button type="button" className="primary new-source-button" disabled={!!busy} onClick={() => setSourceModalOpen(true)}>+ {t("ds.newSource")}</button>

        <div className="rail-divider" />
        <div className="section-title"><h2>{t("ds.sources")}</h2><span>{sources.length}</span></div>
        {!isNarrow && <div className="dataset-sources">{sources.map(item => <button key={item.id} className={`dataset-source ${sourceId === item.id ? "selected" : ""}`} disabled={!!busy} onClick={() => setSourceId(item.id)}>
          <strong>{item.name}</strong>
          <small>{item.kind} · {t("ds.mediaCounts", { images: item.images, videos: item.videos })} · {item.status}{item.error ? ` · ${item.error}` : ""}</small>
        </button>)}
          {!sources.length && (sourcesLoaded ? <p className="muted">{t("ds.noSources")}</p> : <p className="muted"><span className="spinner" /> {t("common.loadingData")}</p>)}
        </div>}
      </aside>
      <main className="main-panel">
        <PageHeader
          eyebrow={t("ds.title")}
          title={source?.name || t("ds.sources")}
          subtitle={t("ds.subtitle")}
          aside={<div className="section-actions">
            <span className="narrow-only"><ContextSelector
              label={t("ds.sources")}
              options={sources.map(item => ({ id: item.id, name: item.name, hint: item.status }))}
              value={sourceId}
              onChange={setSourceId}
              disabled={!!busy}
            /></span>
            {images.length ? <span className="library-count">{t("ip.imagesCount", { count: images.length })}</span> : undefined}
          </div>}
        />
        {active && source.status !== "classifying" && <p className="memory-status" role="status"><span className="spinner" />{source.status === "importing" ? t("ds.queueImporting", { imported: source.imported, total: source.total || "?" }) : t("ds.queuePending")}</p>}
        {active && source.status === "importing" && <ProgressSummary
          label={t("ds.queueImporting", { imported: source.imported, total: source.total || "?" })}
          completed={source.imported}
          pending={Math.max(0, (source.total || 0) - source.imported)}
          failed={0}
          total={source.total}
          showCounts={false}
          showLabel={false}
        />}
        {source?.status === "classifying" && <div className="classify-row" role="status">
          <span className="spinner" />
          <span>{t("ds.queueClassifying", { classified: source.classified, total: source.total })}</span>
          <span className="muted">{t("ds.classifyCounts", { ready: source.ready, pending: source.pending, failed: source.failed })}</span>
          {classifyJob?.progress?.total ? <span className="muted">{t("jobs.eta", { time: formatDuration(Math.max(1, ((Date.now() - new Date(classifyJob.started_at || classifyJob.created_at).getTime()) / 1000) * ((classifyJob.progress.total - (classifyJob.progress.current || 0)) / Math.max(1, classifyJob.progress.current || 0)))) })}</span> : <span className="muted">{t("jobs.etaEstimating")}</span>}
          <Link className="text-button" to="/jobs?type=dataset_classify">{t("ds.viewJob")}</Link>
        </div>}
        {source?.status === "stalled" && <p className="warning" role="status">{t("ds.stalled", { count: source.pending + source.failed })}</p>}
        {source?.status === "failed" && source.error && <p className="warning" role="status">{source.error}</p>}
        {source && !active && source.status !== "stalled" && (source.pending > 0 || source.failed > 0) && <p className="readiness-line">{t("ds.queueReady", { count: source.ready })}{source.pending > 0 ? ` · ${t("ds.queueWaiting", { count: source.pending })}` : ""}{source.failed > 0 ? ` · ${t("ds.queueFailed", { count: source.failed })}` : ""}{source.skipped > 0 ? ` · ${t("ds.skipped", { skipped: source.skipped })}` : ""}</p>}
        <div className="library-toolbar">
          <button className={source && (source.pending > 0 || source.status === "stalled") ? "primary" : undefined} disabled={!!busy || !source} onClick={classifySource}>{source?.status === "stalled" ? t("ds.resumeClassify") : source?.status === "failed" ? t("ds.retryClassify") : t("ds.classifyPending")}</button>
          <input className="filter-input" value={imageSearch} disabled={!!busy} onChange={e => setImageSearch(e.target.value)} placeholder={t("ds.searchImages")} aria-label={t("ds.searchImages")} maxLength={80} />
          <select className="saved-filter-select" value={imageStatusFilter} disabled={!!busy} onChange={e => setImageStatusFilter(e.target.value)} aria-label={t("ip.statusFilter")}>
            <option value="">{t("ip.statusAll")}</option>
            <option value="ready">{t("ds.status.ready")}</option>
            <option value="pending">{t("ds.status.pending")}</option>
            <option value="failed">{t("ds.status.failed")}</option>
          </select>
          <OverflowMenu label={t("common.more")}>
            <button disabled={!!busy || !source} onClick={exportSource}>{t("ds.export")}</button>
            <button disabled={!!busy || !source} onClick={generateProfile}>{t("ds.profile")}</button>
            <button className="danger" disabled={!!busy || !source} onClick={() => source && removeSource(source)}>{t("common.delete")}</button>
          </OverflowMenu>
          {busy && <span className="memory-status" role="status"><span className="spinner" />{busy}</span>}
        </div>
        <div className="library-scroll">
          <AsyncBoundary
            loading={!sourcesLoaded}
            empty={!images.length}
            skeleton="grid"
            loadingText={t("common.loadingData")}
            emptyState={<EmptyState symbol="◎" title={t("ds.noImages")} />}
          >
          <div className="library-grid">{visibleImages.map(item => <article className={`library-card status-${item.status === "ready" ? "approved" : item.status === "failed" || item.status === "blocked" ? "rejected" : ""}`} key={item.id}>
            <DatasetThumb item={item} select={() => setSelected(item)} videoLabel={t("ds.video")} />
            <div className="library-meta">
              <p>{item.caption || item.filename}</p>
              {!!item.tags.length && <div className="library-tags">{item.tags.slice(0, 8).map(tag => <span key={tag}>{tag}</span>)}</div>}
              <div className="library-actions">
                <button onClick={() => setSelected(item)}>{t("ds.details")}</button>
                <button disabled={!!busy} onClick={() => openViewer(item)}>{t("ds.openMedia")}</button>
                <OverflowMenu label={t("common.more")}><button className="danger" disabled={!!busy} onClick={() => removeImage(item)}>{t("common.delete")}</button></OverflowMenu>
              </div>
            </div>
          </article>)}</div>
          {imagesHasMore && <div className="load-more"><button disabled={!!busy} onClick={loadMoreImages}>{t("common.loadMore")}</button></div>}
          </AsyncBoundary>
        </div>
      </main>
      <button type="button" className="narrow-only details-toggle" onClick={() => setDetailsOpen(true)}>{t("ds.details")}</button>
      {isNarrow
        ? <InspectorDrawer open={detailsOpen} onClose={() => setDetailsOpen(false)} title={t("ds.details")} closeLabel={t("common.close")}>{detailsContent}</InspectorDrawer>
        : <aside className="inspector dataset-inspector">{detailsContent}</aside>}
    </div>
    {sourceModalOpen && <div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true" aria-label={t("ds.newSource")}>
      <div className="section-title"><h2>{t("ds.newSource")}</h2><button type="button" onClick={() => setSourceModalOpen(false)} aria-label={t("common.close")}>×</button></div>
      <div className="ip-form">
          <div className="ip-form">
          <label>{t("ds.name")}<input value={name} disabled={!!busy} onChange={e => setName(e.target.value)} maxLength={120} /></label>
          <label>{t("ds.kind")}<select value={kind} disabled={!!busy} onChange={e => setKind(e.target.value as "telegram" | "urls" | "folder" | "x" | "nextcloud")}><option value="telegram">{t("ds.kind.telegram")}</option><option value="urls">{t("ds.kind.urls")}</option><option value="folder">{t("ds.kind.folder")}</option><option value="x">{t("ds.kind.x")}</option><option value="nextcloud">{t("ds.kind.nextcloud")}</option></select></label>
          <label>{t("ds.reference")}<textarea rows={3} value={reference} disabled={!!busy} onChange={e => setReference(e.target.value)} placeholder={kind === "telegram" ? t("ds.reference.telegram") : kind === "urls" ? t("ds.reference.urls") : kind === "x" ? t("ds.reference.x") : kind === "nextcloud" ? t("ds.reference.nextcloud") : t("ds.reference.folder")} maxLength={20000} /></label>
          <label>{t("ds.limit")}<input type="number" min="1" max="2000" value={limit} disabled={!!busy} onChange={e => setLimit(Math.max(1, Math.min(2000, Number(e.target.value))))} /></label>
          <label className="auto-label">{t("ds.classify")} <input type="checkbox" checked={classify} disabled={!!busy} onChange={e => setClassify(e.target.checked)} /></label>
            <button className="primary" disabled={!!busy || !name.trim() || !reference.trim()} onClick={createSource}>{t("ds.create")}</button>
          </div>
      </div>
    </div></div>}
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} video={viewer.video} onClose={() => setViewer(null)} />}
    {profileDraft && <div className="modal-backdrop"><div className="modal fan-editor" role="dialog" aria-modal="true" aria-label={t("ds.profileTitle")}>
      <h2>{t("ds.profileTitle")}</h2>
      <div className="draft-preview">{Object.entries(profileDraft).map(([key, value]) => <div key={key}><strong>{key}</strong><p>{value}</p></div>)}</div>
      <label>{t("ds.characterName")}<input value={characterName} onChange={e => setCharacterName(e.target.value)} maxLength={120} /></label>
      <div className="modal-actions"><button type="button" onClick={() => setProfileDraft(null)} disabled={!!busy}>{t("common.cancel")}</button><button className="primary" disabled={!!busy || !characterName.trim()} onClick={createCharacter}>{t("ds.createCharacter")}</button></div>
    </div></div>}
  </div>;
}
