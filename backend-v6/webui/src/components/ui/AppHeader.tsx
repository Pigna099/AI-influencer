import { Link } from "react-router-dom";
import { useI18n } from "../../i18n";

const LINKS = [
  { to: "/", key: "pg.nav.home" },
  { to: "/chat", key: "pg.nav.chat" },
  { to: "/images", key: "pg.nav.images" },
  { to: "/video", key: "pg.nav.video" },
  { to: "/dataset", key: "pg.nav.dataset" },
  { to: "/loras", key: "pg.nav.loras" },
] as const;

interface Props {
  current: string;
  onLogout: () => void;
  busy?: boolean;
  label?: string;
}

export default function AppHeader({ current, onLogout, busy, label }: Props) {
  const { t } = useI18n();
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v6</b></h1></div>
      <div className="top-actions">
        {label && <span className="sandbox-label">{label}</span>}
        <nav className="top-nav" aria-label={t("pg.navAria")}>
          {LINKS.map(link => (
            <Link key={link.to} className={link.to === current ? "selected" : undefined} aria-current={link.to === current ? "page" : undefined} to={link.to}>{t(link.key)}</Link>
          ))}
        </nav>
        <button onClick={onLogout} disabled={!!busy}>{t("pg.logout")}</button>
      </div>
    </header>
  );
}
