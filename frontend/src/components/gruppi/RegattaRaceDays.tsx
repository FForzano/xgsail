import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { regattasService, racedaysService, racesService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { fmtDate } from "@/utils/format";
import type { UUID } from "@/types";

/** Regatta race-day/race management: create/delete race days and races
 * within a regatta. Shared between the inline expandable block in
 * `ClubEvents` (the club's unified Eventi tab) and the dedicated regatta
 * detail page, so the two don't duplicate this logic. */
export function RegattaRaceDays({ regattaId, manage }: { regattaId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [newDay, setNewDay] = useState("");

  const regatta = useQuery({
    queryKey: raceKeys.regatta(regattaId),
    queryFn: () => regattasService.get(regattaId),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: raceKeys.regatta(regattaId) });

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
    onSuccess: (_data, { dayId }) => queryClient.invalidateQueries({ queryKey: raceKeys.raceday(dayId) }),
    onError: (err: unknown) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const removeDay = useMutation({
    mutationFn: (dayId: UUID) => racedaysService.remove(dayId),
    onSuccess: invalidate,
    onError: (err: unknown) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });
  const removeRace = useMutation({
    mutationFn: ({ raceId }: { raceId: UUID; dayId: UUID }) => racesService.remove(raceId),
    onSuccess: (_data, { dayId }) => queryClient.invalidateQueries({ queryKey: raceKeys.raceday(dayId) }),
    onError: (err: unknown) => notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error"),
  });

  if (!regatta.data) return null;

  return (
    <div className="sf-strip">
      {(regatta.data.race_days ?? []).map((day) => (
        <RaceDayRow
          key={day.id}
          dayId={day.id}
          date={day.date}
          manage={manage}
          addingRace={addRace.isPending}
          onAddRace={(num) => addRace.mutate({ dayId: day.id, num })}
          onRemoveDay={() => {
            if (window.confirm(t("regate.confirmDeleteRaceDay"))) removeDay.mutate(day.id);
          }}
          onRemoveRace={(raceId) => {
            if (window.confirm(t("regate.confirmDeleteRace"))) removeRace.mutate({ raceId, dayId: day.id });
          }}
        />
      ))}
      {manage && (
        <form
          style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}
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
            {t("common.add")}
          </Button>
        </form>
      )}
    </div>
  );
}

function RaceDayRow({
  dayId,
  date,
  manage,
  addingRace,
  onAddRace,
  onRemoveDay,
  onRemoveRace,
}: {
  dayId: UUID;
  date: string;
  manage: boolean;
  addingRace: boolean;
  onAddRace: (num: number) => void;
  onRemoveDay: () => void;
  onRemoveRace: (raceId: UUID) => void;
}) {
  const { t } = useTranslation();
  const day = useQuery({ queryKey: raceKeys.raceday(dayId), queryFn: () => racedaysService.get(dayId) });
  const races = day.data?.races ?? [];

  return (
    <div className="sf-strip__item sf-strip__item--muted" style={{ flexWrap: "wrap" }}>
      <span>
        <strong>{fmtDate(date)}</strong>
      </span>
      <span className="sf-strip__actions" style={{ flexWrap: "wrap" }}>
        {races.map((r) => (
          <span key={r.id} className="sf-strip__actions" style={{ gap: "0.15rem" }}>
            <Link to={`/diario/regate/race/${r.id}`}>
              <Button variant="ghost" className="sf-btn--sm">
                {t("regate.raceNumber")} {r.race_number}
              </Button>
            </Link>
            {manage && (
              <Button
                variant="ghost"
                className="sf-btn--icon-sm"
                aria-label={t("regate.deleteRace")}
                onClick={() => onRemoveRace(r.id)}
              >
                <Trash2 size={13} />
              </Button>
            )}
          </span>
        ))}
        {manage && (
          <Button
            className="sf-btn--sm"
            disabled={addingRace}
            onClick={() => onAddRace((races[races.length - 1]?.race_number ?? 0) + 1)}
          >
            + {t("regate.newRace")}
          </Button>
        )}
        {manage && (
          <Button
            variant="ghost"
            className="sf-btn--icon-sm"
            aria-label={t("regate.deleteRaceDay")}
            onClick={onRemoveDay}
          >
            <Trash2 size={14} />
          </Button>
        )}
      </span>
    </div>
  );
}
