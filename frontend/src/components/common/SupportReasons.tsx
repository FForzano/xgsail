import { useTranslation } from "react-i18next";

export function SupportReasons() {
  const { t } = useTranslation();
  return (
    <ul className="sf-muted">
      <li>{t("support.fundApp")}</li>
      <li>{t("support.fundPublish")}</li>
      <li>{t("support.fundScale")}</li>
    </ul>
  );
}
