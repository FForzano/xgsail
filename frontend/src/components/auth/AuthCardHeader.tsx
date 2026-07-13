import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

/** Shared brand header for the login/register cards — links back to the landing page. */
export function AuthCardHeader() {
  const { t } = useTranslation();
  return (
    <Link to="/" className="sf-authcard__header">
      <img src="/logo.svg" alt="" className="sf-authcard__logo" />
      <h1 className="sf-authcard__brand">XGSail</h1>
      <p className="sf-authcard__tagline">{t("common.tagline")}</p>
    </Link>
  );
}
