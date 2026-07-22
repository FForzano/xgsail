import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { Avatar } from "@/components/ui/Avatar";
import { Popover } from "@/components/ui/Popover";
import { canShowSupportLinks } from "@/config/platform";
import type { ImageRef } from "@/types";

/** Desktop navbar avatar — click opens a dropdown with the profile sub-pages
 * and logout, so the navbar itself only shows the round picture. */
export function ProfileMenu({
  profileImage,
  firstName,
  lastName,
  email,
}: {
  profileImage?: ImageRef | null;
  firstName?: string | null;
  lastName?: string | null;
  email?: string | null;
}) {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();

  return (
    <Popover
      title={email ?? undefined}
      panelClassName="sf-optionsmenu__panel"
      trigger={({ open, toggle }) => (
        <button
          type="button"
          className="sf-navbar__avatarbtn"
          aria-label={t("nav.profilo")}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggle}
        >
          <Avatar size="sm" profileImage={profileImage} firstName={firstName} lastName={lastName} />
        </button>
      )}
    >
      {({ close }) => (
        <>
          <NavLink to="/profilo/anagrafica" className="sf-optionsmenu__item" role="menuitem" onClick={close}>
            {t("profile.myProfile")}
          </NavLink>
          <NavLink to="/profilo/password" className="sf-optionsmenu__item" role="menuitem" onClick={close}>
            {t("profile.changePassword")}
          </NavLink>
          <NavLink to="/profilo/barche" className="sf-optionsmenu__item" role="menuitem" onClick={close}>
            {t("profile.boats")}
          </NavLink>
          <NavLink to="/profilo/devices" className="sf-optionsmenu__item" role="menuitem" onClick={close}>
            {t("profile.devices")}
          </NavLink>
          {/* Store builds use the app stores' own donation systems instead. */}
          {canShowSupportLinks && (
            <NavLink to="/profilo/info" className="sf-optionsmenu__item" role="menuitem" onClick={close}>
              {t("profile.info")}
            </NavLink>
          )}
          <button
            type="button"
            role="menuitem"
            className="sf-optionsmenu__item sf-optionsmenu__item--danger"
            onClick={async () => {
              close();
              await logout();
              navigate("/login");
            }}
          >
            {t("auth.logout")}
          </button>
        </>
      )}
    </Popover>
  );
}
