import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { canShowSupportLinks } from "@/config/platform";

export function ProfiloLayout() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <SectionLayout
      tabs={[
        { to: "/profilo/anagrafica", label: t("profile.details") },
        { to: "/profilo/password", label: t("profile.password") },
        { to: "/profilo/barche", label: t("profile.boats") },
        { to: "/profilo/devices", label: t("profile.devices") },
        // Store builds use the app stores' own donation systems instead.
        ...(canShowSupportLinks ? [{ to: "/profilo/info", label: t("profile.info") }] : []),
      ]}
      footer={
        // Desktop logs out from the navbar avatar dropdown; mobile has no
        // such dropdown, so it keeps a logout button at the page bottom.
        <div className="sf-mobile-only sf-profilo__logout">
          <Button variant="danger" className="sf-btn--sm" onClick={onLogout}>
            {t("auth.logout")}
          </Button>
        </div>
      }
    />
  );
}
