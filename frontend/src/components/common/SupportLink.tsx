import { useTranslation } from "react-i18next";
import { BUY_ME_A_COFFEE_URL } from "@/config/links";

export function SupportLink({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <a href={BUY_ME_A_COFFEE_URL} target="_blank" rel="noreferrer" className={className}>
      ☕ {t("support.cta")}
    </a>
  );
}
