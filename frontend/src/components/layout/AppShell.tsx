import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { ToastViewport } from "@/components/ui/ToastViewport";
import { Avatar } from "@/components/ui/Avatar";
import { ProfileMenu } from "@/components/layout/ProfileMenu";
import { usersService, userKeys } from "@/services/users";
import { unitsStore } from "@/stores/unitsStore";

// The main navigation exposes ONLY the 3 macro-sections (plus Admin) as
// inline links — sub-pages are reached from inside each section
// (docs/frontend-project.md, "Navigazione principale"). Profilo isn't a
// nav link: on desktop it's the avatar dropdown (ProfileMenu), on mobile
// it's the avatar entry in the bottom action bar. Logout lives in the
// ProfileMenu dropdown on desktop and at the bottom of the Profilo page on
// mobile (see ProfiloLayout.tsx).
export function AppShell() {
  const { t } = useTranslation();
  const { user } = useAuth();
  // Resolved profile_image URL isn't on the auth capabilities payload, only
  // on /users/me — same query key as AnagraficaPage so it's cached, not
  // re-fetched.
  const me = useQuery({
    queryKey: userKeys.me,
    queryFn: usersService.me,
    enabled: !!user,
  });

  // The profile's unit_system is the source of truth; sync it into the
  // local store once loaded so it follows the account across devices.
  useEffect(() => {
    if (me.data?.unit_system && me.data.unit_system !== unitsStore.get()) {
      unitsStore.set(me.data.unit_system);
    }
  }, [me.data?.unit_system]);

  const sections = [
    { to: "/diario", label: t("nav.diario"), icon: "📔" },
    { to: "/gruppi", label: t("nav.gruppi"), icon: "👥" },
    { to: "/profilo", label: t("nav.profilo"), icon: "👤" },
    ...(user?.is_superadmin
      ? [{ to: "/admin", label: t("nav.admin"), icon: "⚙️" }]
      : []),
  ];
  const navLinkSections = sections.filter((s) => s.to !== "/profilo");

  return (
    <div className="sf-shell">
      <header className="sf-navbar">
        <NavLink to="/" className="sf-navbar__brand">
          <img src="/logo.svg" alt="" className="sf-navbar__logo" />
          XGSail
        </NavLink>
        <nav className="sf-navbar__links" aria-label="Main">
          {navLinkSections.map((s) => (
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
        <ProfileMenu
          profileImage={me.data?.profile_image ?? null}
          firstName={user?.first_name}
          lastName={user?.last_name}
          email={user?.email}
        />
      </header>
      <main className="sf-main">
        <Outlet />
      </main>
      <nav className="sf-actionbar" aria-label="Main">
        {sections.map((s) => (
          <NavLink key={s.to} to={s.to} className="sf-actionbar__item">
            {s.to === "/profilo" ? (
              <Avatar
                size="sm"
                className="sf-actionbar__avatar"
                profileImage={me.data?.profile_image ?? null}
                firstName={user?.first_name}
                lastName={user?.last_name}
              />
            ) : (
              <span className="sf-actionbar__icon" aria-hidden>
                {s.icon}
              </span>
            )}
            <span className="sf-actionbar__label">{s.label}</span>
          </NavLink>
        ))}
      </nav>
      <ToastViewport />
    </div>
  );
}
