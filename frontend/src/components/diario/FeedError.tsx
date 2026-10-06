import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import styles from "./EventRow.module.css";

/** A diary feed that failed to load, said as such — never the empty state,
 * which on a marina connection would read as a lost upload. */
export function FeedError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className={styles.feedError}>
      <span className="sf-muted">{t("diario.feedError")}</span>
      <Button variant="ghost" className="sf-btn--sm" onClick={onRetry}>
        {t("common.retry")}
      </Button>
    </div>
  );
}
