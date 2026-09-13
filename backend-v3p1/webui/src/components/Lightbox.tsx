import { useEffect } from "react";
import { useI18n } from "../i18n";

export default function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  const { t } = useI18n();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="lightbox" role="dialog" aria-modal="true" aria-label={alt} onClick={onClose}>
    <button className="lightbox-close" onClick={onClose} aria-label={t("common.close")}>×</button>
    <img src={src} alt={alt} onClick={event => event.stopPropagation()} />
    <span className="lightbox-hint">{t("lightbox.hint")}</span>
  </div>;
}
