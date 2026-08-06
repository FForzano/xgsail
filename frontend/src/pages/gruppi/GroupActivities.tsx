import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone } from "lucide-react";
import { activitiesService, activityKeys } from "@/services/activities";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { RichTextField } from "@/components/ui/RichTextField";
import { PostComposer } from "@/components/gruppi/PostComposer";
import { fmtDateTime } from "@/utils/format";
import type { Activity, UUID } from "@/types";
import { useGroupContext } from "./GroupDetailLayout";

function ActivityRow({ a, groupId, canAnnounce }: { a: Activity; groupId: UUID; canAnnounce: boolean }) {
  const { t } = useTranslation();
  const [announcing, setAnnouncing] = useState(false);
  return (
    <div className="sf-strip__item sf-strip__item--muted">
      <span>
        <Link to={`/diario/activities/${a.id}`}>
          <strong>{a.name ?? t(`activities.types.${a.type}`)}</strong>
        </Link>{" "}
        <span className="sf-muted">{fmtDateTime(a.started_at)}</span>
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span className="sf-badge">{t(`activities.types.${a.type}`)}</span>
        {canAnnounce && (
          <Button
            variant="ghost"
            className="sf-btn--icon-sm"
            aria-label={t("gruppi.announceEvent")}
            onClick={() => setAnnouncing(true)}
          >
            <Megaphone size={14} />
          </Button>
        )}
      </span>
      {announcing && (
        <Modal title={t("gruppi.announceEvent")} onClose={() => setAnnouncing(false)}>
          <PostComposer
            ownerType="group"
            ownerId={groupId}
            eventRef={{ kind: "activity", id: a.id }}
            onDone={() => setAnnouncing(false)}
            flush
          />
        </Modal>
      )}
    </div>
  );
}

export function GroupActivities() {
  const { groupId, manages } = useGroupContext();
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [newActivity, setNewActivity] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", started_at: "" });

  const planned = useQuery({
    queryKey: activityKeys.list({ group_id: groupId, status: "planned" }),
    queryFn: () => activitiesService.list({ group_id: groupId, status: "planned" }),
  });
  const past = useQuery({
    queryKey: activityKeys.list({ group_id: groupId, status: "completed" }),
    queryFn: () => activitiesService.list({ group_id: groupId, status: "completed" }),
  });

  const createActivity = useMutation({
    mutationFn: () =>
      activitiesService.create({
        name: form.name,
        description: form.description || null,
        started_at: form.started_at ? new Date(form.started_at).toISOString() : null,
        type: "training",
        group_id: groupId,
        visibility: "group",
        status: "planned",
      }),
    onSuccess: async () => {
      setNewActivity(false);
      setForm({ name: "", description: "", started_at: "" });
      await queryClient.invalidateQueries({ queryKey: activityKeys.all });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <>
      {manages && (
        <div className="sf-toolbar" style={{ justifyContent: "flex-end" }}>
          <Button className="sf-btn--sm" onClick={() => setNewActivity(true)}>
            {t("gruppi.newActivity")}
          </Button>
        </div>
      )}
      <h3>{t("activities.upcoming")}</h3>
      {planned.data?.length ? (
        <div className="sf-strip">
          {planned.data.map((a) => (
            <ActivityRow key={a.id} a={a} groupId={groupId} canAnnounce={manages} />
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("activities.empty")}</p>
      )}

      <h3>{t("activities.past")}</h3>
      {past.data?.length ? (
        <div className="sf-strip">
          {past.data.map((a) => (
            <ActivityRow key={a.id} a={a} groupId={groupId} canAnnounce={manages} />
          ))}
        </div>
      ) : (
        <p className="sf-muted">{t("activities.empty")}</p>
      )}

      {newActivity && (
        <Modal
          title={t("gruppi.newActivity")}
          onClose={() => setNewActivity(false)}
          size="wide"
          footer={
            <div className="sf-form__actions">
              <Button
                type="submit"
                form="act-create-form"
                disabled={createActivity.isPending || !form.name || !form.started_at}
              >
                {t("common.create")}
              </Button>
            </div>
          }
        >
          <form
            id="act-create-form"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              createActivity.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="act-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <InputField
              label={t("activities.when")}
              id="act-when"
              type="datetime-local"
              value={form.started_at}
              onChange={(e) => setForm((f) => ({ ...f, started_at: e.target.value }))}
              required
            />
            <RichTextField
              label={t("common.description")}
              id="act-desc"
              value={form.description}
              onChange={(html) => setForm((f) => ({ ...f, description: html }))}
              tier="basic"
            />
          </form>
        </Modal>
      )}
    </>
  );
}
