import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { regattasService, racedaysService, racesService, raceKeys } from "@/services/races";
import { activitiesService, activityKeys } from "@/services/activities";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { fmtDate, fmtDateTime } from "@/utils/format";
import type { Activity, Regatta, UUID } from "@/types";

/** Regatta management inside the unified Eventi tab (create regatta → race
 * days → races). Marks/results live on the race dashboard, linked per race. */
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

type EventItem =
  | { kind: "regatta"; id: UUID; title: string; date: string | null; endDate: string | null; regatta: Regatta }
  | { kind: "activity"; id: UUID; title: string; date: string | null; endDate: null; activity: Activity };

function EventRow({
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
  return (
    <div>
      <div className="sf-strip__item">
        <span>
          <span
            className={`sf-badge ${item.kind === "regatta" ? "sf-badge--regatta" : "sf-badge--activity"}`}
          >
            {t(`gruppi.eventKind.${item.kind}`)}
          </span>{" "}
          {item.kind === "activity" ? (
            <Link to={`/diario/activities/${item.id}`}>
              <strong>{item.title}</strong>
            </Link>
          ) : (
            <strong>{item.title}</strong>
          )}{" "}
          <span className="sf-muted">
            {item.kind === "regatta"
              ? `${fmtDate(item.date)}${item.endDate && item.endDate !== item.date ? ` – ${fmtDate(item.endDate)}` : ""}`
              : fmtDateTime(item.date)}
          </span>
        </span>
        {item.kind === "regatta" && (
          <Button variant="ghost" className="sf-btn--sm" onClick={onToggle}>
            {open ? t("common.close") : t("regate.raceDays")}
          </Button>
        )}
      </div>
      {item.kind === "activity" && item.activity.description && (
        <p className="sf-muted" style={{ margin: "0.25rem 0 0.5rem" }}>
          {item.activity.description}
        </p>
      )}
      {item.kind === "regatta" && open && <RegattaBlock regattaId={item.id} manage={manage} />}
    </div>
  );
}

export function ClubEvents({ clubId, manage }: { clubId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [creatingRegatta, setCreatingRegatta] = useState(false);
  const [creatingActivity, setCreatingActivity] = useState(false);
  const [regattaForm, setRegattaForm] = useState({ name: "", start_date: "", end_date: "" });
  const [activityForm, setActivityForm] = useState({ name: "", description: "", started_at: "" });
  const [openRegattaId, setOpenRegattaId] = useState<UUID | null>(null);

  const regattas = useQuery({
    queryKey: [...raceKeys.regattas, clubId],
    queryFn: () => regattasService.list(clubId),
  });
  const activities = useQuery({
    queryKey: activityKeys.list({ club_id: clubId }),
    queryFn: () => activitiesService.list({ club_id: clubId }),
  });

  const createRegatta = useMutation({
    mutationFn: () =>
      regattasService.create({
        name: regattaForm.name,
        club_id: clubId,
        start_date: regattaForm.start_date || null,
        end_date: regattaForm.end_date || null,
      }),
    onSuccess: async () => {
      setCreatingRegatta(false);
      setRegattaForm({ name: "", start_date: "", end_date: "" });
      await queryClient.invalidateQueries({ queryKey: raceKeys.regattas });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const createActivity = useMutation({
    mutationFn: () =>
      activitiesService.create({
        name: activityForm.name,
        description: activityForm.description || null,
        started_at: activityForm.started_at ? new Date(activityForm.started_at).toISOString() : null,
        type: "training",
        club_id: clubId,
        visibility: "club",
        status: "planned",
      }),
    onSuccess: async () => {
      setCreatingActivity(false);
      setActivityForm({ name: "", description: "", started_at: "" });
      await queryClient.invalidateQueries({ queryKey: activityKeys.all });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const now = Date.now();
  const items: EventItem[] = [
    ...(regattas.data ?? []).map((r): EventItem => ({
      kind: "regatta",
      id: r.id,
      title: r.name,
      date: r.start_date,
      endDate: r.end_date,
      regatta: r,
    })),
    ...(activities.data ?? []).map((a): EventItem => ({
      kind: "activity",
      id: a.id,
      title: a.name ?? t(`activities.types.${a.type}`),
      date: a.started_at,
      endDate: null,
      activity: a,
    })),
  ];

  const upcoming = items
    .filter((i) => (i.kind === "activity" ? i.activity.status === "planned" : i.date && new Date(i.date).getTime() >= now))
    .sort((a, b) => new Date(a.date ?? 0).getTime() - new Date(b.date ?? 0).getTime());
  const past = items
    .filter((i) => (i.kind === "activity" ? i.activity.status === "completed" : !(i.date && new Date(i.date).getTime() >= now)))
    .sort((a, b) => new Date(b.date ?? 0).getTime() - new Date(a.date ?? 0).getTime());

  return (
    <Card
      title={t("gruppi.events")}
      actions={
        manage && (
          <span className="sf-strip__actions">
            <Button className="sf-btn--sm" onClick={() => setCreatingRegatta(true)}>
              {t("regate.newRegatta")}
            </Button>
            <Button className="sf-btn--sm" onClick={() => setCreatingActivity(true)}>
              {t("gruppi.newEvent")}
            </Button>
          </span>
        )
      }
    >
      <h3>{t("gruppi.upcomingEvents")}</h3>
      {upcoming.length ? (
        <div className="sf-strip">
          {upcoming.map((i) => (
            <EventRow
              key={`${i.kind}-${i.id}`}
              item={i}
              manage={manage}
              open={openRegattaId === i.id}
              onToggle={() => setOpenRegattaId(openRegattaId === i.id ? null : i.id)}
            />
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("gruppi.emptyEvents")}</p>
      )}

      <h3>{t("gruppi.pastEvents")}</h3>
      {past.length ? (
        <div className="sf-strip">
          {past.map((i) => (
            <EventRow
              key={`${i.kind}-${i.id}`}
              item={i}
              manage={manage}
              open={openRegattaId === i.id}
              onToggle={() => setOpenRegattaId(openRegattaId === i.id ? null : i.id)}
            />
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("gruppi.emptyEvents")}</p>
      )}

      {creatingRegatta && (
        <Modal title={t("regate.newRegatta")} onClose={() => setCreatingRegatta(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              createRegatta.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="r-name"
              value={regattaForm.name}
              onChange={(e) => setRegattaForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <div className="sf-form__row">
              <InputField
                label={t("sessions.start")}
                id="r-start"
                type="date"
                value={regattaForm.start_date}
                onChange={(e) => setRegattaForm((f) => ({ ...f, start_date: e.target.value }))}
              />
              <InputField
                label={t("sessions.end")}
                id="r-end"
                type="date"
                value={regattaForm.end_date}
                onChange={(e) => setRegattaForm((f) => ({ ...f, end_date: e.target.value }))}
              />
            </div>
            <div className="sf-form__actions">
              <Button type="submit" disabled={createRegatta.isPending || !regattaForm.name}>
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {creatingActivity && (
        <Modal title={t("gruppi.newEvent")} onClose={() => setCreatingActivity(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              createActivity.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="a-name"
              value={activityForm.name}
              onChange={(e) => setActivityForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <InputField
              label={t("gruppi.eventWhen")}
              id="a-when"
              type="datetime-local"
              value={activityForm.started_at}
              onChange={(e) => setActivityForm((f) => ({ ...f, started_at: e.target.value }))}
              required
            />
            <TextAreaField
              label={t("gruppi.eventDescription")}
              id="a-desc"
              value={activityForm.description}
              onChange={(e) => setActivityForm((f) => ({ ...f, description: e.target.value }))}
            />
            <div className="sf-form__actions">
              <Button
                type="submit"
                disabled={createActivity.isPending || !activityForm.name || !activityForm.started_at}
              >
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
