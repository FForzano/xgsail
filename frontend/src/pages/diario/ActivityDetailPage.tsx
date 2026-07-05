import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { useAuth } from "@/hooks/useAuth";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtDateTime } from "@/utils/format";
import { sessionStatusBadge } from "./SessionsPage";
import type { UUID } from "@/types";

export function ActivityDetailPage() {
  const { activityId } = useParams<{ activityId: UUID }>();
  const { t } = useTranslation();
  const { user } = useAuth();
  const { can, isSuperadmin } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const [markForm, setMarkForm] = useState({ mark_role: "", lat: "", lng: "" });

  const activity = useQuery({
    queryKey: activityKeys.detail(activityId!),
    queryFn: () => activitiesService.get(activityId!),
    enabled: !!activityId,
  });
  const sessions = useQuery({
    queryKey: activityKeys.sessions(activityId!),
    queryFn: () => activitiesService.sessions(activityId!),
    enabled: !!activityId,
  });
  const marks = useQuery({
    queryKey: activityKeys.marks(activityId!),
    queryFn: () => activitiesService.marks(activityId!),
    enabled: !!activityId,
  });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });

  const addMark = useMutation({
    mutationFn: () =>
      activitiesService.addMark(activityId!, {
        mark_role: markForm.mark_role,
        lat: Number(markForm.lat),
        lng: Number(markForm.lng),
      }),
    onSuccess: async () => {
      setMarkForm({ mark_role: "", lat: "", lng: "" });
      await queryClient.invalidateQueries({ queryKey: activityKeys.marks(activityId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeMark = useMutation({
    mutationFn: (markId: UUID) => activitiesService.removeMark(activityId!, markId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: activityKeys.marks(activityId!) }),
  });
  const removeActivity = useMutation({
    mutationFn: () => activitiesService.remove(activityId!),
    onSuccess: () => navigate("/diario/activities"),
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (activity.isLoading || !activityId) return <Spinner />;
  if (!activity.data) return null;
  const a = activity.data;
  const canEdit =
    isSuperadmin ||
    a.created_by === user?.id ||
    (a.club_id != null && can("activity.manage", a.club_id));
  const boatName = (id: string) => boats.data?.find((b) => b.id === id)?.name ?? "—";

  return (
    <div className="sf-section__body">
      <Card
        title={
          <>
            {a.name ?? t(`activities.types.${a.type}`)}{" "}
            <span className="sf-badge">{t(`activities.types.${a.type}`)}</span>{" "}
            <span className="sf-badge">{t(`activities.visibility.${a.visibility}`)}</span>
          </>
        }
        actions={
          canEdit && (
            <Button variant="danger" className="sf-btn--sm" onClick={() => setDeleting(true)}>
              {t("common.delete")}
            </Button>
          )
        }
      >
        <p className="sf-muted">
          {fmtDateTime(a.started_at)} — {fmtDateTime(a.ended_at)}
        </p>
        {a.race_id && (
          <p>
            <Link to={`/diario/regate/race/${a.race_id}`}>{t("regate.open")}</Link>
          </p>
        )}
      </Card>

      <Card title={t("activities.sessions")}>
        {sessions.data?.length ? (
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th>{t("sessions.boat")}</th>
                  <th>{t("sessions.start")}</th>
                  <th>{t("common.status")}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.data.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/diario/sessioni/${s.id}`}>{boatName(s.boat_id)}</Link>
                    </td>
                    <td>{fmtDateTime(s.started_at)}</td>
                    <td>
                      <span className={sessionStatusBadge(s.status)}>{s.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
      </Card>

      <Card title={t("activities.marks")}>
        {marks.data?.length ? (
          <div className="sf-strip">
            {marks.data.map((m) => (
              <div key={m.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{m.mark_role}</strong>{" "}
                  <span className="sf-muted">
                    {m.lat.toFixed(5)}, {m.lng.toFixed(5)}
                  </span>
                </span>
                {canEdit && (
                  <Button
                    variant="ghost"
                    className="sf-btn--sm"
                    onClick={() => removeMark.mutate(m.id)}
                  >
                    {t("common.remove")}
                  </Button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="sf-muted">{t("common.none")}</p>
        )}
        {canEdit && (
          <form
            className="sf-form__row"
            style={{ alignItems: "end", marginTop: "0.75rem" }}
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              addMark.mutate();
            }}
          >
            <InputField
              label={t("activities.markRole")}
              id="mark-role"
              value={markForm.mark_role}
              onChange={(e) => setMarkForm((f) => ({ ...f, mark_role: e.target.value }))}
              placeholder="windward"
              required
            />
            <InputField
              label="Lat"
              id="mark-lat"
              type="number"
              step="any"
              value={markForm.lat}
              onChange={(e) => setMarkForm((f) => ({ ...f, lat: e.target.value }))}
              required
            />
            <InputField
              label="Lng"
              id="mark-lng"
              type="number"
              step="any"
              value={markForm.lng}
              onChange={(e) => setMarkForm((f) => ({ ...f, lng: e.target.value }))}
              required
            />
            <div className="sf-field">
              <Button type="submit" disabled={addMark.isPending}>
                {t("activities.addMark")}
              </Button>
            </div>
          </form>
        )}
      </Card>

      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("activities.deleteConfirm")}
          busy={removeActivity.isPending}
          onConfirm={() => removeActivity.mutate()}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
