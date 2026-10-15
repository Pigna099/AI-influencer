import { useCallback, useEffect, useState } from "react";
import { api, Character, IdentityCandidate, IdentityRun } from "../../api";
import { useI18n } from "../../i18n";
import AsyncBoundary from "./AsyncBoundary";
import StatusBadge from "./StatusBadge";

function CandidateThumb({ candidate, onView }: { candidate: IdentityCandidate; onView: (url: string, alt: string) => void }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    if (!candidate.image_id) return;
    api.fetchBlob(`/api/library/${candidate.image_id}/file?v=${encodeURIComponent(candidate.filename || "")}`)
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
  }, [candidate.image_id, candidate.filename]);
  if (!candidate.image_id) return null;
  return <button type="button" className="identity-thumb" onClick={() => url && onView(url, candidate.angle)} disabled={!url}>
    {url ? <img src={url} alt={candidate.angle} loading="lazy" /> : <span className="spinner" />}
  </button>;
}

export default function IdentityPanel({ character, busy, perform, onView, onError }: {
  character: Character | null;
  busy: boolean;
  perform: (label: string, work: () => Promise<void>) => Promise<void>;
  onView: (url: string, alt: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [run, setRun] = useState<IdentityRun | null>(null);
  const [override, setOverride] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async (characterId: string) => {
    const listing = await api.getIdentityRuns(characterId, 1);
    setRun(listing.length ? await api.getIdentityRun(listing[0].id) : null);
    setLoaded(true);
  }, []);

  useEffect(() => {
    setRun(null);
    setLoaded(false);
    if (!character) return;
    void load(character.id).catch(() => setLoaded(true));
  }, [character?.id, load]);

  if (!character) return null;
  const referenceOnly = character.source_category === "reference_only";
  const hasAnchor = !!character.avatar_filename;

  const generate = () => {
    void perform(t("idr.generating"), async () => {
      const created = await api.createIdentityRun(character.id, {});
      setRun(created);
    });
  };

  const review = (candidate: IdentityCandidate, status: "accepted" | "rejected" | "uncertain") => {
    void (async () => {
      try {
        await api.patchIdentityCandidate(candidate.id, status);
        setRun(current => current ? { ...current, candidates: current.candidates.map(entry => entry.id === candidate.id ? { ...entry, status } : entry) } : current);
      } catch (error) {
        onError(error instanceof Error ? error.message : String(error));
      }
    })();
  };

  const freeze = () => {
    if (!run) return;
    void perform(t("idr.freezing"), async () => {
      try {
        const frozen = await api.freezeIdentityRun(run.id, override);
        setRun(current => current ? { ...current, ...frozen, candidates: current.candidates } : current);
      } catch (error) {
        onError(error instanceof Error ? error.message : String(error));
      }
    });
  };

  const accepted = run?.candidates.filter(candidate => candidate.status === "accepted").length ?? 0;

  return <div className="identity-panel">
    <div className="section-title"><h2>{t("idr.title")}</h2>
      <div className="preset-actions">
        <span className="library-count">{accepted}/{run?.candidates.length ?? 0} {t("idr.accepted")}</span>
        <button disabled={busy || referenceOnly || !hasAnchor} title={referenceOnly ? t("form.referenceOnlyWarning") : !hasAnchor ? t("idr.needAnchor") : undefined} onClick={generate}>{t("idr.generate")}</button>
        {run && run.status !== "frozen" && <button disabled={busy} onClick={freeze}>{t("idr.freeze")}</button>}
      </div>
    </div>
    <p className="muted">{t("idr.hint")}</p>
    {run?.status === "frozen" && <p className="memory-status" role="status">✓ {t("idr.frozen")}{run.override_reason ? ` · ${t("idr.override")}: ${run.override_reason}` : ""}</p>}
    {run && run.status !== "frozen" && <label className="identity-override">{t("idr.overrideLabel")}<input value={override} onChange={e => setOverride(e.target.value)} maxLength={2000} placeholder={t("idr.overridePlaceholder")} /></label>}
    <AsyncBoundary
      loading={!loaded}
      empty={!run}
      loadingText={t("common.loadingData")}
      emptyState={<p className="muted">{t("idr.empty")}</p>}
    >
      {run && <div className="identity-grid">
        {run.candidates.map(candidate => <article className={`identity-card status-${candidate.status}`} key={candidate.id}>
          <CandidateThumb candidate={candidate} onView={onView} />
          <small>{candidate.angle} · {candidate.seed}</small>
          <StatusBadge status={candidate.status === "accepted" ? "approved" : candidate.status === "rejected" ? "rejected" : "draft"} label={t(`idr.status.${candidate.status}` as "idr.status.draft")} />
          <div className="library-actions">
            <button disabled={busy || run.status === "frozen"} onClick={() => review(candidate, "accepted")}>{t("idr.accept")}</button>
            <button disabled={busy || run.status === "frozen"} onClick={() => review(candidate, "rejected")}>{t("idr.reject")}</button>
            <button disabled={busy || run.status === "frozen"} onClick={() => review(candidate, "uncertain")}>{t("idr.uncertain")}</button>
          </div>
        </article>)}
      </div>}
    </AsyncBoundary>
  </div>;
}
