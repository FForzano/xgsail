import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { User, Mail, Code2, ScrollText } from "lucide-react";
import { windKeys, windService } from "@/services/wind";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SupportReasons } from "@/components/common/SupportReasons";
import {
  BUY_ME_A_COFFEE_URL,
  GITHUB_URL,
  LICENSE_URL,
  CONTACT_EMAIL,
  DEVELOPER_GITHUB_URL,
} from "@/config/links";
import styles from "./InfoPage.module.css";

/** Which model/station data the wind estimate is actually built from. Kept on
 * the info page rather than on a page of its own: it belongs with "who made
 * this and under what licence" — it is the same kind of disclosure, and a
 * dedicated page is one nobody would find. The map's stations layer is the
 * other half of this (see components/map/StationsLayer.ts); the models have
 * no position, so they can only be listed here. */
function WindSourcesCard() {
  const { t } = useTranslation();
  const sources = useQuery({ queryKey: windKeys.sources, queryFn: windService.sources });
  const stations = useQuery({
    queryKey: windKeys.stationsWithLast,
    queryFn: () => windService.listStations({ includeLast: true }),
    staleTime: 60 * 1000,
  });

  const models = sources.data?.models ?? [];
  const regional = models.filter((m) => m.kind === "regional");
  const global = models.filter((m) => m.kind === "global");
  const located = (stations.data ?? []).filter((s) => s.lat != null && s.lng != null);

  return (
    <Card title={t("windSources.title")}>
      <p className="sf-muted">{t("windSources.intro")}</p>

      {located.length > 0 && (
        <div className={styles.sourceGroup}>
          <p className={`sf-muted ${styles.sourceLabel}`}>{t("windSources.stations")}</p>
          <ul className={styles.sourceList}>
            {located.map((s) => (
              <li key={s.id}>
                {s.name ?? s.external_station_id}
                {s.last_observation?.tws_kts != null && (
                  <span className={`sf-muted ${styles.sourceReading}`}>
                    {" "}
                    — {s.last_observation.tws_kts} kn
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {regional.length > 0 && (
        <div className={styles.sourceGroup}>
          <p className={`sf-muted ${styles.sourceLabel}`}>{t("windSources.modelsRegional")}</p>
          <ul className={styles.sourceList}>
            {regional.map((m) => (
              <li key={m.id}>{t(`windSources.model.${m.id}`, { defaultValue: m.id })}</li>
            ))}
          </ul>
        </div>
      )}

      {global.length > 0 && (
        <div className={styles.sourceGroup}>
          <p className={`sf-muted ${styles.sourceLabel}`}>{t("windSources.modelsGlobal")}</p>
          <ul className={styles.sourceList}>
            {global.map((m) => (
              <li key={m.id}>{t(`windSources.model.${m.id}`, { defaultValue: m.id })}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="sf-muted">{t("windSources.note")}</p>
    </Card>
  );
}

export function InfoPage() {
  const { t } = useTranslation();

  const aboutRows = [
    {
      icon: User,
      label: t("support.developer"),
      value: (
        <a href={DEVELOPER_GITHUB_URL} target="_blank" rel="noreferrer">
          Federico Forzano
        </a>
      ),
    },
    {
      icon: Mail,
      label: t("support.contact"),
      value: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>,
    },
    {
      icon: Code2,
      label: t("support.sourceCode"),
      value: (
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">
          {GITHUB_URL}
        </a>
      ),
    },
    {
      icon: ScrollText,
      label: t("landing.license"),
      value: (
        <a href={LICENSE_URL} target="_blank" rel="noreferrer">
          Apache 2.0
        </a>
      ),
    },
  ];

  return (
    <div className="sf-grid" style={{ gridTemplateColumns: "minmax(280px, 480px)" }}>
      <Card title={t("support.title")}>
        <p className="sf-muted">{t("support.intro")}</p>
        <p>{t("support.fundsIntro")}</p>
        <SupportReasons />
        <a href={BUY_ME_A_COFFEE_URL} target="_blank" rel="noreferrer">
          <Button>☕ {t("support.cta")}</Button>
        </a>
      </Card>
      <Card title={t("support.aboutTitle")}>
        <div className={styles.aboutList}>
          {aboutRows.map((row) => (
            <div className={styles.aboutRow} key={row.label}>
              <span className={styles.aboutIcon} aria-hidden>
                <row.icon size={16} strokeWidth={2} />
              </span>
              <div>
                <p className={`sf-muted ${styles.aboutLabel}`}>{row.label}</p>
                <p className={styles.aboutValue}>{row.value}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <WindSourcesCard />
    </div>
  );
}
