import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { ToastViewport } from "@/components/ui/ToastViewport";

// The main navigation exposes ONLY the 3 macro-sections (plus Profilo/Admin
// utilities) — sub-pages are reached from inside each section
// (docs/frontend-project.md, "Navigazione principale").
//
// Desktop: links inline in the top navbar. Mobile: the links move to a fixed
// bottom action bar (thumb-reachable); the navbar keeps brand + logout.
export function AppShell() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  const sections = [
    { to: "/diario", label: t("nav.diario"), icon: "📔" },
    { to: "/gruppi", label: t("nav.gruppi"), icon: "👥" },
    { to: "/profilo", label: t("nav.profilo"), icon: "👤" },
    ...(user?.is_superadmin
      ? [{ to: "/admin", label: t("nav.admin"), icon: "⚙️" }]
      : []),
  ];

  return (
    <div className="sf-shell">
      <header className="sf-navbar">
        <NavLink to="/" className="sf-navbar__brand">
          SailFrames
        </NavLink>
        <nav className="sf-navbar__links" aria-label="Main">
          {sections.map((s) => (
            <NavLink
              key={s.to}
              to={s.to}
              className={`sf-navlink ${s.to === "/admin" ? "sf-navlink--admin" : ""}`}
            >
              {s.label}
            </NavLink>
          ))}
        </nav>
        <div className="sf-navbar__spacer" />
        <div className="sf-navbar__user">
          <span className="sf-navbar__email">{user?.email}</span>
          <button className="sf-btn sf-btn--ghost sf-btn--sm" onClick={onLogout}>
            {t("auth.logout")}
          </button>
        </div>
      </header>
      <main className="sf-main">
        <Outlet />
      </main>
      <nav className="sf-actionbar" aria-label="Main">
        {sections.map((s) => (
          <NavLink key={s.to} to={s.to} className="sf-actionbar__item">
            <span className="sf-actionbar__icon" aria-hidden>
              {s.icon}
            </span>
            <span className="sf-actionbar__label">{s.label}</span>
          </NavLink>
        ))}
      </nav>
      <ToastViewport />
    </div>
  );
}
