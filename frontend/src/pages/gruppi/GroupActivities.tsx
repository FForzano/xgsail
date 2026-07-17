import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { activitiesService, activityKeys } from "@/services/activities";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { fmtDateTime } from "@/utils/format";
import { useGroupContext } from "./GroupDetailLayout";

export function GroupActivities() {
  const { groupId, manages } = useGroupContext();
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [newActivity, setNewActivity] = useState(false);
  const [activityName, setActivityName] = useState("");

  const activities = useQuery({
    queryKey: activityKeys.list({ group_id: groupId }),
    queryFn: () => activitiesService.list({ group_id: groupId }),
  });

  const createActivity = useMutation({
    mutationFn: () =>
      activitiesService.create({
        name: activityName,
        type: "training",
        group_id: groupId,
        visibility: "group",
      }),
    onSuccess: async () => {
      setNewActivity(false);
      setActivityName("");
      await queryClient.invalidateQueries({ queryKey: activityKeys.all });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Card
      title={t("gruppi.groupActivities")}
      actions={
        manages && (
          <Button className="sf-btn--sm" onClick={() => setNewActivity(true)}>
            {t("gruppi.newActivity")}
          </Button>
        )
      }
    >
      {activities.data?.length ? (
        <div className="sf-strip">
          {activities.data.map((a) => (
            <div key={a.id} className="sf-strip__item sf-strip__item--muted">
              <span>
                <Link to={`/diario/activities/${a.id}`}>
                  <strong>{a.name ?? t(`activities.types.${a.type}`)}</strong>
                </Link>{" "}
                <span className="sf-muted">{fmtDateTime(a.started_at)}</span>
              </span>
              <span className="sf-badge">{t(`activities.types.${a.type}`)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("activities.empty")}</p>
      )}

      {newActivity && (
        <Modal title={t("gruppi.newActivity")} onClose={() => setNewActivity(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              createActivity.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="act-name"
              value={activityName}
              onChange={(e) => setActivityName(e.target.value)}
              required
            />
            <div className="sf-form__actions">
              <Button type="submit" disabled={createActivity.isPending || !activityName}>
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
