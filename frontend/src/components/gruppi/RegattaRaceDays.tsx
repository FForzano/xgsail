import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus, Trash2, X } from "lucide-react";
import { regattasService, racedaysService, racesService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { InputField } from "@/components/ui/InputField";
import { raceStatusBadge } from "@/utils/badges";
import { fmtDate, fmtTime } from "@/utils/format";
import type { Race, RaceDay, UUID } from "@/types";
import styles from "./RegattaRaceDays.module.css";

/** Regatta race days and their races: read as a schedule (when each race
 * started, how it went), with create/delete on top for organizers. Shared
 * between the inline expandable block in the diario feed (`EventRow`), the
 * regatta detail page's schedule section and that page's race-day management
 * modal, so the three don't duplicate this logic.
 *
 * Reading and organizing want different shapes: `manage` renders every day as
 * its own group with add/remove controls, because a second day has to stay
 * reachable, while the read-only schedule collapses the common club-regatta
 * cases — a single day drops the day header (the date is already in the
 * regatta's meta line) and a single race is surfaced as one row straight into
 * its dashboard, rather than a list of one.
 *
 * Races come from the regatta's own payload (`race_days[].races[]`) — there is
 * deliberately no query per race day here. */
export function RegattaRaceDays({ regattaId, manage }: { regattaId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [newDay, setNewDay] = useState("");
  const [pendingDelete, setPendingDelete] = useState<{
    kind: "day" | "race";
    id: UUID;
  } | null>(null);

  const regatta = useQuery({
    queryKey: raceKeys.regatta(regattaId),
    queryFn: () => regattasService.get(regattaId),
  });
  // The race payload carries status but not results, so the winner's name has
  // to come from the standings — one query for the whole regatta, shared with
  // the standings table, instead of a `races/{id}` fetch per chip.
  const standings = useQuery({
    queryKey: raceKeys.standings(regattaId),
    queryFn: () => regattasService.standings(regattaId),
  });

  // Races are added and removed inside the regatta's own payload, so every
  // mutation here invalidates the regatta — not a per-race-day key.
  const invalidate = () => queryClient.invalidateQueries({ queryKey: raceKeys.regatta(regattaId) });
  const onError = (err: unknown) =>
    notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error");

  const addDay = useMutation({
    mutationFn: (date: string) => racedaysService.create({ regatta_id: regattaId, date }),
    onSuccess: async () => {
      setNewDay("");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const addRace = useMutation({
    mutationFn: ({ dayId, num }: { dayId: UUID; num: number }) =>
      racesService.create({ race_day_id: dayId, race_number: num }),
    onSuccess: invalidate,
    onError,
  });
  const removeDay = useMutation({
    mutationFn: (dayId: UUID) => racedaysService.remove(dayId),
    onSuccess: async () => {
      setPendingDelete(null);
      await invalidate();
    },
    onError,
  });
  const removeRace = useMutation({
    mutationFn: (raceId: UUID) => racesService.remove(raceId),
    onSuccess: async () => {
      setPendingDelete(null);
      await invalidate();
    },
    onError,
  });

  /** Race id → winning boat's name, for the races that have results. */
  const winners = useMemo(() => {
    const byRace = new Map<UUID, string>();
    for (const row of standings.data?.standings ?? []) {
      for (const [raceId, result] of Object.entries(row.races)) {
        if (result.position === 1) byRace.set(raceId, row.boat.name);
      }
    }
    return byRace;
  }, [standings.data]);

  if (!regatta.data) return null;

  const deleting = removeDay.isPending || removeRace.isPending;
  const days = regatta.data.race_days ?? [];
  const soloDay = !manage && days.length === 1 ? days[0] : null;

  const renderRaces = (day: RaceDay, solo: boolean) => {
    const races = day.races ?? [];
    if (races.length === 0 && !manage) return <p className="sf-muted">{t("regate.racesEmpty")}</p>;
    return (
      <ul className={`sf-strip ${styles.races}`}>
        {races.map((race) => (
          <RaceRow
            key={race.id}
            race={race}
            winner={winners.get(race.id) ?? null}
            manage={manage}
            highlight={solo && races.length === 1}
            onRemove={() => setPendingDelete({ kind: "race", id: race.id })}
          />
        ))}
        {manage && (
          <li>
            <button
              className={styles.addRace}
              disabled={addRace.isPending}
              onClick={() => addRace.mutate({ dayId: day.id, num: nextRaceNumber(days) })}
            >
              <Plus size={14} /> {t("regate.newRace")}
            </button>
          </li>
        )}
      </ul>
    );
  };

  return (
    <div className={styles.days}>
      {days.length === 0 && <EmptyState>{t("regate.raceDaysEmpty")}</EmptyState>}

      {soloDay
        ? renderRaces(soloDay, true)
        : days.map((day) => (
            <div key={day.id} className={styles.day}>
              <div className={styles.dayHead}>
                <span className={styles.dayDate}>{fmtDate(day.date)}</span>
                {manage && (
                  <button
                    className={styles.iconBtn}
                    aria-label={t("regate.deleteRaceDay")}
                    onClick={() => setPendingDelete({ kind: "day", id: day.id })}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
              {renderRaces(day, false)}
            </div>
          ))}

      {manage && (
        <form
          className={styles.addDayForm}
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (newDay) addDay.mutate(newDay);
          }}
        >
          <InputField
            label={t("regate.newRaceDay")}
            id={`day-${regattaId}`}
            type="date"
            value={newDay}
            onChange={(e) => setNewDay(e.target.value)}
          />
          <Button type="submit" className="sf-btn--sm" disabled={addDay.isPending || !newDay}>
            <Plus size={14} /> {t("common.add")}
          </Button>
        </form>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={t(pendingDelete.kind === "day" ? "regate.deleteRaceDay" : "regate.deleteRace")}
          message={t(
            pendingDelete.kind === "day"
              ? "regate.confirmDeleteRaceDay"
              : "regate.confirmDeleteRace",
          )}
          busy={deleting}
          onClose={() => setPendingDelete(null)}
          onConfirm={() =>
            pendingDelete.kind === "day"
              ? removeDay.mutate(pendingDelete.id)
              : removeRace.mutate(pendingDelete.id)
          }
        />
      )}
    </div>
  );
}

/** Race numbers run across the whole regatta, not per day, so the next one
 * follows the highest already scheduled anywhere in it. */
function nextRaceNumber(days: Array<{ races?: Race[] }>): number {
  let max = 0;
  for (const day of days) {
    for (const race of day.races ?? []) max = Math.max(max, race.race_number);
  }
  return max + 1;
}

function RaceRow({
  race,
  winner,
  manage,
  highlight,
  onRemove,
}: {
  race: Race;
  winner: string | null;
  manage: boolean;
  /** The regatta's only race: reads as the race itself, not as a list entry. */
  highlight: boolean;
  onRemove: () => void;
}) {
  const { t } = useTranslation();

  return (
    <li className={`sf-strip__item ${highlight ? "sf-strip__item--active" : ""}`}>
      <Link className={styles.raceLink} to={`/diario/regate/race/${race.id}`}>
        <span className={styles.raceNumber}>
          {t("regate.raceNumber")} {race.race_number}
        </span>
        <span className={styles.raceOutcome}>
          {winner ? `1° ${winner}` : t("regate.awaitingResults")}
        </span>
      </Link>
      <span className="sf-strip__actions">
        {race.start_time && (
          <span className={styles.raceTime}>{fmtTime(new Date(race.start_time).getTime())}</span>
        )}
        <span className={`${raceStatusBadge(race.status)} sf-badge--sm`}>
          {t(`race.status.${race.status}`)}
        </span>
        {manage ? (
          <button className={styles.iconBtn} aria-label={t("regate.deleteRace")} onClick={onRemove}>
            <X size={15} />
          </button>
        ) : (
          <ChevronRight className={styles.chevron} size={16} aria-hidden />
        )}
      </span>
    </li>
  );
}
