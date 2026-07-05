import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { regattasService, racedaysService, racesService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { fmtDate } from "@/utils/format";
import type { Regatta, UUID } from "@/types";

/** Regatta management inside the club page (create regatta → race days →
 * races). Marks/results live on the race dashboard, linked per race. */
function RegattaBlock({ regattaId, manage }: { regattaId: UUID; manage: boolean }) {
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
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
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
          onAddRace={(num) => addRace.mutate({ dayId: day.id, num })}
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
  onAddRace,
}: {
  dayId: UUID;
  date: string;
  manage: boolean;
  onAddRace: (num: number) => void;
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
          <Link key={r.id} to={`/diario/regate/race/${r.id}`}>
            <Button variant="ghost" className="sf-btn--sm">
              {t("regate.raceNumber")} {r.race_number}
            </Button>
          </Link>
        ))}
        {manage && (
          <Button
            className="sf-btn--sm"
            onClick={() => onAddRace((races[races.length - 1]?.race_number ?? 0) + 1)}
          >
            + {t("regate.newRace")}
          </Button>
        )}
      </span>
    </div>
  );
}

export function ClubRegattas({ clubId, manage }: { clubId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "" });
  const [open, setOpen] = useState<UUID | null>(null);

  const regattas = useQuery({
    queryKey: [...raceKeys.regattas, clubId],
    queryFn: () => regattasService.list(clubId),
  });

  const create = useMutation({
    mutationFn: () =>
      regattasService.create({
        name: form.name,
        club_id: clubId,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      }),
    onSuccess: async () => {
      setCreating(false);
      setForm({ name: "", start_date: "", end_date: "" });
      await queryClient.invalidateQueries({ queryKey: raceKeys.regattas });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Card
      title={t("gruppi.regattas")}
      actions={
        manage && (
          <Button className="sf-btn--sm" onClick={() => setCreating(true)}>
            {t("regate.newRegatta")}
          </Button>
        )
      }
    >
      {regattas.data?.length === 0 && <p className="sf-muted">{t("regate.empty")}</p>}
      <div className="sf-strip">
        {regattas.data?.map((r: Regatta) => (
          <div key={r.id}>
            <div className="sf-strip__item">
              <span>
                <strong>{r.name}</strong>{" "}
                <span className="sf-muted">
                  {fmtDate(r.start_date)}
                  {r.end_date && r.end_date !== r.start_date ? ` – ${fmtDate(r.end_date)}` : ""}
                </span>
              </span>
              <Button
                variant="ghost"
                className="sf-btn--sm"
                onClick={() => setOpen(open === r.id ? null : r.id)}
              >
                {open === r.id ? t("common.close") : t("regate.raceDays")}
              </Button>
            </div>
            {open === r.id && <RegattaBlock regattaId={r.id} manage={manage} />}
          </div>
        ))}
      </div>

      {creating && (
        <Modal title={t("regate.newRegatta")} onClose={() => setCreating(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="r-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <div className="sf-form__row">
              <InputField
                label={t("sessions.start")}
                id="r-start"
                type="date"
                value={form.start_date}
                onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              />
              <InputField
                label={t("sessions.end")}
                id="r-end"
                type="date"
                value={form.end_date}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
              />
            </div>
            <div className="sf-form__actions">
              <Button type="submit" disabled={create.isPending || !form.name}>
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
