import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="sf-section">
      <h1>404</h1>
      <p className="sf-muted">{t("errors.notFound")}</p>
      <Link to="/">{t("common.backHome")}</Link>
    </div>
  );
}
