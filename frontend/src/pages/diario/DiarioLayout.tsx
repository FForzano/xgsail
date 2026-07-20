import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";

export function DiarioLayout() {
  const { t } = useTranslation();
  return (
    <SectionLayout
      tabs={[
        { to: "/diario/personale", label: t("diario.myDiary") },
        { to: "/diario/circoli", label: t("diario.clubsDiary") },
      ]}
    />
  );
}
