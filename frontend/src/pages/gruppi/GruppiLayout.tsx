import { useTranslation } from "react-i18next";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { MembershipStrip } from "@/components/membership/MembershipStrip";
import { EntitySearch } from "@/components/gruppi/EntitySearch";

export function GruppiLayout() {
  const { t } = useTranslation();
  return (
    <SectionLayout
      header={
        <>
          <EntitySearch />
          <MembershipStrip />
        </>
      }
      tabs={[
        { to: "/gruppi/gruppi", label: t("gruppi.groups"), dataTour: "gruppi-tabs" },
        { to: "/gruppi/clubs", label: t("gruppi.clubs") },
      ]}
    />
  );
}
