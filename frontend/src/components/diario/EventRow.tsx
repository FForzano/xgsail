import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sailboat, Trophy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import { fmtDate, fmtDateTime } from "@/utils/format";
import type { Activity, Regatta, UUID } from "@/types";
import styles from "./EventRow.module.css";

/** Who/what an activity or regatta is attributed to, shown as an extra badge
 * next to the kind badge (personal vs. club vs. group — color + text, not
 * just color, per the diario redesign). */
export type Ownership = { kind: "personal" | "club" | "group"; name?: string };

export type EventItem =
  | {
      kind: "regatta";
      id: UUID;
      title: string;
      date: string | null;
      endDate: string | null;
      regatta: Regatta;
      ownership?: Ownership;
    }
  | {
      kind: "activity";
      id: UUID;
      title: string;
      date: string | null;
      endDate: null;
      activity: Activity;
      ownership?: Ownership;
    };

/** One activity/regatta rendered as a social-feed-style post card, shared by
 * the club "Eventi" tab and the two diario tabs (Personale / Circoli e
 * gruppi): cover image (or a kind-tinted placeholder), kind + ownership
 * badges, title (linking to the activity/regatta detail page), date and a
 * description preview. Regattas additionally get an inline race-days
 * toggle. */
export function EventRow({
  item,
  manage,
  open,
  onToggle,
}: {
  item: EventItem;
  manage: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const description = item.kind === "activity" ? item.activity.description : item.regatta.description;
  const href = item.kind === "activity" ? `/diario/activities/${item.id}` : `/diario/regate/regatta/${item.id}`;
  const imageUrl = item.kind === "activity" ? item.activity.thumbnail?.url : item.regatta.image?.url;

  return (
    <article className={styles.card}>
      <Link to={href} className={styles.mediaLink}>
        {imageUrl ? (
          <img src={imageUrl} alt="" className={styles.media} />
        ) : (
          <div className={styles.mediaPlaceholder} data-kind={item.kind} aria-hidden>
            {item.kind === "regatta" ? <Trophy size={32} /> : <Sailboat size={32} />}
          </div>
        )}
      </Link>
      <div className={styles.body}>
        <div className={styles.badges}>
          <span className={`sf-badge ${item.kind === "regatta" ? "sf-badge--regatta" : "sf-badge--activity"}`}>
            {t(`gruppi.eventKind.${item.kind}`)}
          </span>
          {item.ownership && (
            <span className={`sf-badge sf-badge--${item.ownership.kind}`}>
              {t(`diario.ownership.${item.ownership.kind}`)}
              {item.ownership.name ? `: ${item.ownership.name}` : ""}
            </span>
          )}
        </div>
        <Link to={href} className={styles.title}>
          {item.title}
        </Link>
        <span className={styles.meta}>
          {item.kind === "regatta"
            ? `${fmtDate(item.date)}${item.endDate && item.endDate !== item.date ? ` – ${fmtDate(item.endDate)}` : ""}`
            : fmtDateTime(item.date)}
        </span>
        {description && <p className={styles.description}>{description}</p>}
        {item.kind === "regatta" && (
          <div className={styles.footer}>
            <Button variant="ghost" className="sf-btn--sm" onClick={onToggle}>
              {open ? t("common.close") : t("regate.raceDays")}
            </Button>
          </div>
        )}
      </div>
      {item.kind === "regatta" && open && (
        <div className={styles.expanded}>
          <RegattaRaceDays regattaId={item.id} manage={manage} />
        </div>
      )}
    </article>
  );
}
