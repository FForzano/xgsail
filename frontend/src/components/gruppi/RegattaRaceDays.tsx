import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { regattasService, racedaysService, racesService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InputField } from "@/components/ui/InputField";
import { raceStatusBadge } from "@/utils/badges";
import { fmtDate, fmtTime } from "@/utils/format";
import type { Race, UUID } from "@/types";
import styles from "./RegattaRaceDays.module.css";

/** Regatta race days and their races: read as a schedule (when each race
 * started, how it went), with create/delete on top for organizers. Shared
 * between the inline expandable block in the diario feed (`EventRow`) and the
 * regatta detail page, so the two don't duplicate this logic.
 *
 * Races come from the regatta's own payload (`race_days[].races[]`) — there is
 * deliberately no query per race day here. */
export function RegattaRaceDays({ regattaId, manage }: { regattaId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [newDay, setNewDay] = useState("");
  const [pendingDelete, setPendingDelete] = useState<
    { kind: "day" | "race"; id: UUID } | null
  >(null);

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

  return (
    <div className={styles.days}>
      {(regatta.data.race_days ?? []).map((day) => (
        <div key={day.id} className={styles.dayCard}>
          <div className={styles.dayCardHead}>
            <span className={styles.dayCardDate}>{fmtDate(day.date)}</span>
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
          <div className={styles.raceGrid}>
            {(day.races ?? []).map((race) => (
              <RaceCard
                key={race.id}
                race={race}
                winner={winners.get(race.id) ?? null}
                manage={manage}
                onRemove={() => setPendingDelete({ kind: "race", id: race.id })}
              />
            ))}
            {manage && (
              <button
                className={styles.addCard}
                disabled={addRace.isPending}
                onClick={() =>
                  addRace.mutate({
                    dayId: day.id,
                    num: nextRaceNumber(regatta.data?.race_days ?? []),
                  })
                }
              >
                <Plus size={14} /> {t("regate.newRace")}
              </button>
            )}
          </div>
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

function RaceCard({
  race,
  winner,
  manage,
  onRemove,
}: {
  race: Race;
  winner: string | null;
  manage: boolean;
  onRemove: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className={styles.raceCard}>
      <Link className={styles.raceLink} to={`/diario/regate/race/${race.id}`}>
        <span className={styles.raceHead}>
          <span className={styles.raceNumber}>
            {t("regate.raceNumber")} {race.race_number}
          </span>
          <span className={`${raceStatusBadge(race.status)} sf-badge--sm`}>
            {t(`race.status.${race.status}`)}
          </span>
        </span>
        <span className={styles.raceTime}>
          {race.start_time ? fmtTime(new Date(race.start_time).getTime()) : "—"}
        </span>
        <span className={styles.raceOutcome}>
          {winner ? `1° ${winner}` : t("regate.awaitingResults")}
        </span>
      </Link>
      {manage && (
        <button className={styles.raceRemove} aria-label={t("regate.deleteRace")} onClick={onRemove}>
          <X size={13} />
        </button>
      )}
    </div>
  );
}
