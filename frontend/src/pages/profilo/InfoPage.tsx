import { useTranslation } from "react-i18next";
import { User, Mail, Code2, ScrollText } from "lucide-react";
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
    </div>
  );
}
