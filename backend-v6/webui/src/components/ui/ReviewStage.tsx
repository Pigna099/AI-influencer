import { useEffect, useState } from "react";
import { api, LibraryImage } from "../../api";
import { useI18n } from "../../i18n";

export default function ReviewStage({ item, index, total, anchorUrl, overlay, sibling, busy, onStatus, onLabel, onRating, onNavigate, onView }: {
  item: LibraryImage;
  index: number;
  total: number;
  anchorUrl: string;
  overlay: boolean;
  sibling?: LibraryImage;
  busy: boolean;
  onStatus: (item: LibraryImage, status: "approved" | "rejected" | "draft") => void;
  onLabel: (item: LibraryImage, label: "sfw" | "suggestive" | "explicit") => void;
  onRating: (item: LibraryImage, rating: number) => void;
  onNavigate: (direction: -1 | 1) => void;
  onView: (url: string, alt: string) => void;
}) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [overlaySibling, setOverlaySibling] = useState(false);
  const [siblingUrl, setSiblingUrl] = useState("");

  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setSiblingUrl("");
    if (!overlaySibling || !sibling) return;
    api.fetchBlob(`/api/library/${sibling.id}/thumb?v=${encodeURIComponent(sibling.filename)}`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setSiblingUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [overlaySibling, sibling?.id, sibling?.filename]);

  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    api.fetchBlob(`/api/library/${item.id}/file?v=${encodeURIComponent(item.filename)}`)
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
  }, [item.id, item.filename]);

  return <div className="review-layout">
    <div className="review-stage">
      <div className="review-image">
        {url ? <img src={url} alt={item.caption || item.prompt} onClick={() => onView(url, item.caption || item.prompt)} /> : <span className="spinner" />}
        {overlay && anchorUrl && <img className="review-overlay" src={anchorUrl} alt="" aria-hidden="true" />}
        {overlaySibling && siblingUrl && <img className="review-overlay review-overlay-sibling" src={siblingUrl} alt="" aria-hidden="true" />}
        <button type="button" className="review-prev" disabled={busy || index <= 0} onClick={() => onNavigate(-1)} aria-label={t("ip.review.prev")}>‹</button>
        <button type="button" className="review-next" disabled={busy || index >= total - 1} onClick={() => onNavigate(1)} aria-label={t("ip.review.next")}>›</button>
      </div>
      <div className="review-controls">
        <span className="library-stars" role="group" aria-label={t("ip.rating")}>{[1, 2, 3, 4, 5].map(value => <button key={value} className={item.rating >= value ? "on" : ""} disabled={busy} onClick={() => onRating(item, value)} aria-label={`${value}/5`}>★</button>)}</span>
        <button disabled={busy} className={item.status === "approved" ? "selected" : undefined} onClick={() => onStatus(item, item.status === "approved" ? "draft" : "approved")}>{t("ip.approve")} <kbd>A</kbd></button>
        <button disabled={busy} className={item.status === "rejected" ? "selected" : undefined} onClick={() => onStatus(item, item.status === "rejected" ? "draft" : "rejected")}>{t("ip.reject")} <kbd>R</kbd></button>
        {sibling && <label className="auto-label"><input type="checkbox" checked={overlaySibling} onChange={e => setOverlaySibling(e.target.checked)} /> {t("ip.review.overlayPrev")}</label>}
        <label className="review-label">{t("ip.contentLabel")}<select value={item.content_label || "suggestive"} disabled={busy} onChange={e => onLabel(item, e.target.value as "sfw" | "suggestive" | "explicit")}>
          <option value="sfw">{t("ip.label.sfw")}</option>
          <option value="suggestive">{t("ip.label.suggestive")}</option>
          <option value="explicit">{t("ip.label.explicit")}</option>
        </select></label>
        <small className="review-counter">{index + 1} / {total}</small>
      </div>
      <details className="review-meta"><summary>{t("ip.review.metadata")}</summary>
        <p className="review-caption">{item.caption || item.prompt}</p>
        <small className="muted">{item.style} · {(item.checkpoint || "").replace(".safetensors", "")} · {t("ip.used")} {item.used_count} · seed {item.seed}</small>
      </details>
      <details className="review-help"><summary>{t("ip.review.help")}</summary><small className="muted">{t("ip.review.shortcuts")}</small></details>
    </div>
  </div>;
}
