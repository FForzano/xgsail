import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";

export function ProfiloLayout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <SectionLayout
      header={
        // On mobile the top navbar is gone — identity + logout live here.
        <div className="sf-mobile-only sf-strip__item sf-strip__item--muted">
          <span className="sf-muted">{user?.email}</span>
          <Button variant="ghost" className="sf-btn--sm" onClick={onLogout}>
            {t("auth.logout")}
          </Button>
        </div>
      }
      tabs={[
        { to: "/profilo/anagrafica", label: t("profile.details") },
        { to: "/profilo/password", label: t("profile.password") },
        { to: "/profilo/barche", label: t("profile.boats") },
        { to: "/profilo/devices", label: t("profile.devices") },
      ]}
    />
  );
}
