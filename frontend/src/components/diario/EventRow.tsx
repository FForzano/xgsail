import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Camera, Megaphone } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ResultsRow } from "@/components/ui/ResultsRow";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import { PostComposer } from "@/components/gruppi/PostComposer";
import { RichText } from "@/components/ui/RichText";
import { fmtDistance, fmtDuration, fmtTime } from "@/utils/format";
import type { Activity, Regatta, UUID } from "@/types";
import styles from "./EventRow.module.css";

/** Who/what an activity or regatta is attributed to, shown as an extra badge
 * next to the kind badge (personal vs. club vs. group — color + text, not
 * just color, per the diario redesign). */
export type Ownership = {
  // "crew" = an outing someone else created that I was aboard for; it reaches
  // my diary through session_crew, not through authorship.
  kind: "personal" | "crew" | "club" | "group";
  name?: string;
};

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

/** Calendar day key in local time — two entries on the same day share one
 * date mark in the logbook margin. */
function dayKey(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function isUpcoming(iso: string | null): boolean {
  return !!iso && new Date(iso).getTime() > Date.now();
}

/** Whether `items[index]` opens a new day in the logbook (and so carries the
 * date mark in the margin). Feeds are newest-first, so this compares with
 * the entry right above. */
export function opensDay(items: EventItem[], index: number): boolean {
  return index === 0 || dayKey(items[index].date) !== dayKey(items[index - 1].date);
}

/** One activity/regatta as a logbook entry, shared by the club "Eventi" tab
 * and the two diario tabs (Personale / Circoli e gruppi): the day in the
 * margin (only on the first entry of that day — see `opensDay`), then the
 * title and its codes, the track render as the entry's main image, one ruled
 * line of figures and a short description. Regattas additionally get an
 * inline race-days toggle. */
export function EventRow({
  item,
  showDay = true,
  manage,
  open,
  onToggle,
  clubId,
  canAnnounce,
  dataTour,
}: {
  item: EventItem;
  /** False for a second entry on the same day: the margin stays empty and
   * the entry sits under a hairline instead of the day's ink rule. */
  showDay?: boolean;
  manage: boolean;
  open: boolean;
  onToggle: () => void;
  /** Club owning this event — required together with `canAnnounce` to show
   * the "announce" action (regattas/group activities aren't announced from
   * here, see `ClubEvents.tsx`/`GroupActivities.tsx`). */
  clubId?: UUID;
  canAnnounce?: boolean;
  /** `data-tour` anchor — set only on one row (the first) by callers that
   * use this in a guided-tour step, so the step highlights a single entry
   * rather than the whole feed. */
  dataTour?: string;
}) {
  const { t } = useTranslation();
  const [announcing, setAnnouncing] = useState(false);
  const description = item.kind === "activity" ? item.activity.description : item.regatta.description;
  const href = item.kind === "activity" ? `/diario/activities/${item.id}` : `/diario/regate/regatta/${item.id}`;
  // The track render is what identifies an outing at a glance — where it went
  // and what shape it was — so it stays the entry's main image and the photo
  // rides along as an inset. A photo only takes the main slot when there is
  // no track to show (a manual activity, a worker render that never landed),
  // where it beats the tinted placeholder. A regatta has one hero image and
  // no track at all.
  const track = item.kind === "activity" ? item.activity.thumbnail : null;
  const photo = item.kind === "activity" ? item.activity.cover_photo : null;
  const inset = track && photo ? photo : null;
  const imageUrl =
    item.kind === "activity"
      ? (track?.url ?? photo?.url)
      : item.regatta.image?.url;
  const isPhoto = item.kind === "activity" && !track && !!photo;
  const photoCount = item.kind === "activity" ? item.activity.photo_count : 0;

  return (
    <article className={styles.entry} data-opens-day={showDay || undefined} data-tour={dataTour}>
      <div className={styles.margin}>{showDay && <DayMark iso={item.date} />}</div>
      <div className={styles.main}>
        <header className={styles.head}>
          <Link to={href} className={styles.title}>
            {item.title}
          </Link>
          <span className={styles.codes}>
            <span className={`sf-badge ${item.kind === "regatta" ? "sf-badge--regatta" : "sf-badge--activity"}`}>
              {t(`gruppi.eventKind.${item.kind}`)}
            </span>
            {item.ownership && (
              <span className={`sf-badge sf-badge--${item.ownership.kind}`}>
                {t(`diario.ownership.${item.ownership.kind}`)}
                {item.ownership.name ? `: ${item.ownership.name}` : ""}
              </span>
            )}
          </span>
        </header>

        {/* No picture, no box: a logbook entry has no row height to keep
            equal with its neighbours, and a tinted 4/3 stand-in would be the
            largest thing on the page while saying nothing. */}
        {imageUrl && (
          <Link to={href} className={styles.mediaLink} tabIndex={-1} aria-hidden>
            <div className={styles.mediaBox}>
              {/* Absolutely positioned inside a fixed-aspect-ratio box, not
                  sized via the <img>'s own intrinsic dimensions — those vary
                  per track (a long thin route vs. a squarish one), which made
                  entries with different track shapes different heights. */}
              <img
                src={imageUrl}
                alt=""
                loading="lazy"
                className={styles.media}
                data-fit={isPhoto ? "photo" : "track"}
              />
              {inset && (
                // The photo lifted off the track as its own tile rather than
                // shown beside it: splitting the 4/3 slot would shrink both
                // images instead of letting the track stay readable.
                <span className={styles.inset}>
                  <img src={inset.url} alt="" loading="lazy" className={styles.insetImg} />
                  {photoCount > 1 && <PhotoTally count={photoCount} small />}
                </span>
              )}
              {isPhoto && photoCount > 1 && <PhotoTally count={photoCount} />}
            </div>
          </Link>
        )}

        <EntryFigures item={item} />
        {/* Only an event still ahead keeps its description: that is where an
            organiser puts the logistics (meeting time, briefing). A past
            outing's notes are one tap away on its own page. */}
        {isUpcoming(item.date) && <RichText html={description} tier="basic" className={styles.description} />}

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
        {item.kind === "regatta" && open && (
          <div className={styles.expanded}>
            <RegattaRaceDays regattaId={item.id} manage={manage} />
          </div>
        )}
      </div>
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

/** The day as a noticeboard date stamp: weekday, a large day numeral, month.
 * Set in the margin, so a run of outings reads down the page by date. */
export function DayMark({ iso }: { iso: string | null }) {
  const { i18n } = useTranslation();
  const parts = useMemo(() => {
    if (!iso) return null;
    const d = new Date(iso);
    const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(i18n.language, o).format(d);
    return {
      weekday: fmt({ weekday: "short" }),
      day: fmt({ day: "numeric" }),
      month: fmt({ month: "short" }),
      // Only a past season needs saying; this year's dates read without it.
      year: d.getFullYear() !== new Date().getFullYear() ? fmt({ year: "numeric" }) : null,
    };
  }, [iso, i18n.language]);
  if (!parts) return <span className={styles.day}>—</span>;
  return (
    <time dateTime={iso ?? undefined} className={styles.dayMark}>
      <span className={styles.weekday}>{parts.weekday}</span>
      <span className={styles.day}>{parts.day}</span>
      <span className={styles.month}>{parts.month}</span>
      {parts.year && <span className={styles.year}>{parts.year}</span>}
    </time>
  );
}

/** The entry's ruled line: start time, duration, distance, and the session
 * count when an outing holds several (then distance is per boat, so it isn't
 * shown). A regatta prints its date range instead. */
function EntryFigures({ item }: { item: EventItem }) {
  const { t, i18n } = useTranslation();
  if (item.kind === "regatta") {
    return <ResultsRow compact cells={[[t("diario.entry.dates"), DayRange(item.date, item.endDate, i18n.language)]]} />;
  }
  const a = item.activity;
  const cells: Array<[string, string]> = [];
  if (a.started_at) cells.push([t("diario.entry.time"), fmtTime(new Date(a.started_at).getTime()).slice(0, 5)]);
  const durationS =
    a.duration_s ??
    (a.started_at && a.ended_at ? (new Date(a.ended_at).getTime() - new Date(a.started_at).getTime()) / 1000 : null);
  if (durationS) cells.push([t("sessions.duration"), fmtDuration(durationS)]);
  if (a.session_count > 1) cells.push([t("diario.entry.sessions"), String(a.session_count)]);
  else if (a.distance_m != null) cells.push([t("sessions.distance"), fmtDistance(a.distance_m)]);
  return cells.length ? <ResultsRow compact cells={cells} /> : null;
}

/** A regatta's days as a results sheet prints them: "27–28 ott", the month
 * and year said once, and the year only for a past or future season. */
function DayRange(startIso: string | null, endIso: string | null, locale: string): string {
  if (!startIso) return "—";
  const start = new Date(startIso);
  const end = endIso ? new Date(endIso) : start;
  const thisYear = start.getFullYear() === new Date().getFullYear() && end.getFullYear() === start.getFullYear();
  const withYear: Intl.DateTimeFormatOptions = thisYear ? {} : { year: "numeric" };
  const day = (d: Date, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(locale, o).format(d);
  if (start.toDateString() === end.toDateString()) return day(start, { day: "numeric", month: "short", ...withYear });
  if (start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear()) {
    return `${start.getDate()}–${day(end, { day: "numeric", month: "short", ...withYear })}`;
  }
  return `${day(start, { day: "numeric", month: "short", ...withYear })} – ${day(end, { day: "numeric", month: "short", ...withYear })}`;
}

function PhotoTally({ count, small = false }: { count: number; small?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className={small ? styles.insetCount : styles.photoCount} aria-label={t("sessions.photoCount", { count })}>
      <Camera size={small ? 11 : 12} aria-hidden />
      {count}
    </span>
  );
}
