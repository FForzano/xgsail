import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";

export function DiarioLayout() {
  const { t } = useTranslation();
  return (
    <SectionLayout
      tabs={[
        { to: "/diario/sessioni", label: t("diario.sessions") },
        { to: "/diario/activities", label: t("diario.activities") },
        { to: "/diario/regate", label: t("diario.races") },
      ]}
    />
  );
}
