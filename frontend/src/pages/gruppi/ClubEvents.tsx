import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { regattasService, raceKeys } from "@/services/races";
import { activitiesService, activityKeys } from "@/services/activities";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { EventRow, type EventItem } from "@/components/diario/EventRow";
import feedStyles from "@/components/diario/EventRow.module.css";
import type { UUID } from "@/types";

export function ClubEvents({
  clubId,
  manageRegattas,
  manageActivities,
}: {
  clubId: UUID;
  manageRegattas: boolean;
  manageActivities: boolean;
}) {
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
    queryFn: () => regattasService.list({ clubId }),
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
    // Race-tracking activities (type "race", auto-created off `activities.race_id`
    // the first time a race's sessions/marks are touched, see
    // `backend/routers/races.py::_race_activity`) are internal bookkeeping for
    // that race's GPS data — they're already represented by the race itself
    // under its regatta above, so listing them again here would just duplicate
    // the same race as its own unrelated "event".
    ...(activities.data ?? [])
      .filter((a) => a.type !== "race")
      .map((a): EventItem => ({
        kind: "activity",
        id: a.id,
        title: a.name ?? t(`activities.types.${a.type}`),
        date: a.started_at,
        endDate: null,
        activity: a,
      })),
  ];

  const upcoming = items
    .filter((i) => i.date && new Date(i.date).getTime() >= now)
    .sort((a, b) => new Date(a.date ?? 0).getTime() - new Date(b.date ?? 0).getTime());
  const past = items
    .filter((i) => !(i.date && new Date(i.date).getTime() >= now))
    .sort((a, b) => new Date(b.date ?? 0).getTime() - new Date(a.date ?? 0).getTime());

  return (
    <Card
      title={t("gruppi.events")}
      actions={
        (manageRegattas || manageActivities) && (
          <span className="sf-strip__actions">
            {manageRegattas && (
              <Button className="sf-btn--sm" onClick={() => setCreatingRegatta(true)}>
                {t("regate.newRegatta")}
              </Button>
            )}
            {manageActivities && (
              <Button className="sf-btn--sm" onClick={() => setCreatingActivity(true)}>
                {t("gruppi.newEvent")}
              </Button>
            )}
          </span>
        )
      }
    >
      <h3>{t("gruppi.upcomingEvents")}</h3>
      {upcoming.length ? (
        <div className={feedStyles.feed}>
          {upcoming.map((i) => (
            <EventRow
              key={`${i.kind}-${i.id}`}
              item={i}
              manage={manageRegattas}
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
        <div className={feedStyles.feed}>
          {past.map((i) => (
            <EventRow
              key={`${i.kind}-${i.id}`}
              item={i}
              manage={manageRegattas}
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
