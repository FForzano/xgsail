import { useTranslation } from "react-i18next";
import { BackLink } from "@/components/ui/BackLink";
import { Section } from "@/components/ui/Section";
import { NoteTemplatesManager } from "@/components/notes/NoteTemplatesManager";

export function NoteTemplatesPage() {
  const { t } = useTranslation();
  return (
    <div className="sf-section__body">
      <BackLink to="/profilo/barche" label={t("noteTemplates.backToBoats")} />
      <Section title={t("noteTemplates.title")}>
        <NoteTemplatesManager />
      </Section>
    </div>
  );
}
