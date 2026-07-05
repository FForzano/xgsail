import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { MembershipStrip } from "@/components/membership/MembershipStrip";

export function GruppiLayout() {
  const { t } = useTranslation();
  return (
    <SectionLayout
      header={<MembershipStrip />}
      tabs={[
        { to: "/gruppi/gruppi", label: t("gruppi.groups") },
        { to: "/gruppi/clubs", label: t("gruppi.clubs") },
      ]}
    />
  );
}
