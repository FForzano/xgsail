import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Megaphone, Sailboat, Trophy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import { PostComposer } from "@/components/gruppi/PostComposer";
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
  clubId,
  canAnnounce,
  dataTour,
}: {
  item: EventItem;
  manage: boolean;
  open: boolean;
  onToggle: () => void;
  /** Club owning this event — required together with `canAnnounce` to show
   * the "announce" action (regattas/group activities aren't announced from
   * here, see `ClubEvents.tsx`/`GroupActivities.tsx`). */
  clubId?: UUID;
  canAnnounce?: boolean;
  /** `data-tour` anchor — set only on one row (the first) by callers that
   * use this in a guided-tour step, so the step highlights a single card
   * rather than the whole feed. */
  dataTour?: string;
}) {
  const { t } = useTranslation();
  const [announcing, setAnnouncing] = useState(false);
  const description = item.kind === "activity" ? item.activity.description : item.regatta.description;
  const href = item.kind === "activity" ? `/diario/activities/${item.id}` : `/diario/regate/regatta/${item.id}`;
  const imageUrl = item.kind === "activity" ? item.activity.thumbnail?.url : item.regatta.image?.url;

  return (
    <article className={styles.card} data-tour={dataTour}>
      <Link to={href} className={styles.mediaLink}>
        <div className={styles.mediaBox}>
          {imageUrl ? (
            // Absolutely positioned inside a plain-div fixed-aspect-ratio
            // box, not sized via the <img>'s own aspect-ratio/intrinsic
            // dimensions — those vary per track (a long thin route vs. a
            // squarish one), which was making cards with vs. without a
            // thumbnail (or with different track shapes) different heights.
            <img src={imageUrl} alt="" className={styles.media} />
          ) : (
            <div className={styles.mediaPlaceholder} data-kind={item.kind} aria-hidden>
              {item.kind === "regatta" ? <Trophy size={32} /> : <Sailboat size={32} />}
            </div>
          )}
        </div>
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
        {(item.kind === "regatta" || (canAnnounce && clubId)) && (
          <div className={styles.footer}>
            {item.kind === "regatta" && (
              <Button variant="ghost" className="sf-btn--sm" onClick={onToggle}>
                {open ? t("common.close") : t("regate.raceDays")}
              </Button>
            )}
            {canAnnounce && clubId && (
              <Button variant="ghost" className="sf-btn--sm" onClick={() => setAnnouncing(true)}>
                <Megaphone size={14} /> {t("gruppi.announceEvent")}
              </Button>
            )}
          </div>
        )}
      </div>
      {item.kind === "regatta" && open && (
        <div className={styles.expanded}>
          <RegattaRaceDays regattaId={item.id} manage={manage} />
        </div>
      )}
      {announcing && clubId && (
        <Modal title={t("gruppi.announceEvent")} onClose={() => setAnnouncing(false)}>
          <PostComposer
            ownerType="club"
            ownerId={clubId}
            eventRef={{ kind: item.kind, id: item.id }}
            onDone={() => setAnnouncing(false)}
            flush
          />
        </Modal>
      )}
    </article>
  );
}
