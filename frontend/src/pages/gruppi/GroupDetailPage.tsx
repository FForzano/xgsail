import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { groupsService, groupKeys } from "@/services/groups";
import { activitiesService, activityKeys } from "@/services/activities";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImageUploader } from "@/components/common/ImageUploader";
import { UserPicker } from "@/components/common/UserPicker";
import { userLabel, fmtDateTime } from "@/utils/format";
import type { GroupRole, UUID } from "@/types";

export function GroupDetailPage() {
  const { groupId } = useParams<{ groupId: UUID }>();
  const { t } = useTranslation();
  const { user, refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [inviting, setInviting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [newActivity, setNewActivity] = useState(false);
  const [activityName, setActivityName] = useState("");

  const group = useQuery({
    queryKey: groupKeys.detail(groupId!),
    queryFn: () => groupsService.get(groupId!),
    enabled: !!groupId,
  });
  const activities = useQuery({
    queryKey: activityKeys.list({ group_id: groupId! }),
    queryFn: () => activitiesService.list({ group_id: groupId! }),
    enabled: !!groupId,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: groupKeys.all });
  };

  const invite = useMutation({
    mutationFn: (userId: UUID) => groupsService.addMember(groupId!, { user_id: userId }),
    onSuccess: async () => {
      setInviting(false);
      notify(t("gruppi.joinRequested"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: UUID; role: GroupRole }) =>
      groupsService.updateMember(groupId!, userId, { role }),
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const approve = useMutation({
    mutationFn: (userId: UUID) => groupsService.updateMember(groupId!, userId, { status: "active" }),
    onSuccess: invalidate,
  });
  const removeMember = useMutation({
    mutationFn: (userId: UUID) => groupsService.removeMember(groupId!, userId),
    onSuccess: async () => {
      await invalidate();
      await refreshCaps();
    },
  });
  const removeGroup = useMutation({
    mutationFn: () => groupsService.remove(groupId!),
    onSuccess: async () => {
      await invalidate();
      await refreshCaps();
      navigate("/gruppi/gruppi");
    },
  });
  const createActivity = useMutation({
    mutationFn: () =>
      activitiesService.create({
        name: activityName,
        type: "training",
        group_id: groupId!,
        visibility: "group",
      }),
    onSuccess: async () => {
      setNewActivity(false);
      setActivityName("");
      await queryClient.invalidateQueries({ queryKey: activityKeys.all });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (group.isLoading || !groupId) return <Spinner />;
  if (!group.data) return null;
  const g = group.data;

  const myRow = g.members?.find((m) => m.user_id === user?.id);
  const manages = user?.is_superadmin || myRow?.role === "owner" || myRow?.role === "admin";
  const isOwner = user?.is_superadmin || myRow?.role === "owner";

  return (
    <div className="sf-section__body">
      <Card
        title={
          <>
            {g.profile_image && <img className="sf-avatar" src={g.profile_image.url} alt="" />}{" "}
            {g.name} <span className="sf-badge">{t(`gruppi.${g.visibility}`)}</span>
          </>
        }
        actions={
          isOwner && (
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <ImageUploader
                create={() => groupsService.uploadImage(groupId)}
                confirm={(id) => groupsService.confirmImage(groupId, id)}
                onDone={invalidate}
              />
              <Button variant="danger" className="sf-btn--sm" onClick={() => setDeleting(true)}>
                {t("common.delete")}
              </Button>
            </span>
          )
        }
      >
        <p className="sf-muted">{g.description}</p>
      </Card>

      {g.members && (
        <Card
          title={t("gruppi.members")}
          actions={
            manages && (
              <Button className="sf-btn--sm" onClick={() => setInviting(true)}>
                {t("gruppi.invite")}
              </Button>
            )
          }
        >
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th>{t("common.name")}</th>
                  <th>{t("common.role")}</th>
                  <th>{t("common.status")}</th>
                  {manages && <th />}
                </tr>
              </thead>
              <tbody>
                {g.members.map((m) => (
                  <tr key={m.user_id}>
                    <td>{userLabel(m.user)}</td>
                    <td>
                      {isOwner && m.user_id !== user?.id ? (
                        <Select
                          label=""
                          id={`grole-${m.user_id}`}
                          value={m.role}
                          onChange={(e) =>
                            setRole.mutate({ userId: m.user_id, role: e.target.value as GroupRole })
                          }
                        >
                          {(["owner", "admin", "member"] as GroupRole[]).map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        m.role
                      )}
                    </td>
                    <td>
                      <span
                        className={
                          m.status === "active" ? "sf-badge sf-badge--success" : "sf-badge sf-badge--warning"
                        }
                      >
                        {m.status}
                      </span>
                    </td>
                    {manages && (
                      <td style={{ display: "flex", gap: "0.4rem" }}>
                        {m.status === "requested" && (
                          <Button className="sf-btn--sm" onClick={() => approve.mutate(m.user_id)}>
                            {t("gruppi.approve")}
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          className="sf-btn--sm"
                          onClick={() => removeMember.mutate(m.user_id)}
                        >
                          {m.user_id === user?.id ? t("gruppi.leave") : t("common.remove")}
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

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
      </Card>

      {inviting && (
        <Modal title={t("gruppi.invite")} onClose={() => setInviting(false)}>
          <UserPicker
            busy={invite.isPending}
            pickLabel={t("gruppi.invite")}
            onPick={(u) => invite.mutate(u.id)}
          />
        </Modal>
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
      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("gruppi.deleteGroupConfirm")}
          busy={removeGroup.isPending}
          onConfirm={() => removeGroup.mutate()}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
