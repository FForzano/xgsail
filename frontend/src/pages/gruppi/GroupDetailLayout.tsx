import { useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Trash2 } from "lucide-react";
import { groupsService, groupKeys } from "@/services/groups";
import { useAuth } from "@/hooks/useAuth";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { BackLink } from "@/components/ui/BackLink";
import { ImageUploader } from "@/components/common/ImageUploader";
import { EntityFeed } from "@/components/gruppi/EntityFeed";
import type { Group, UUID } from "@/types";
import entityHeaderStyles from "@/components/gruppi/entityHeader.module.css";

export interface GroupContext {
  groupId: UUID;
  group: Group;
  isMember: boolean;
  manages: boolean;
  isOwner: boolean;
}

export function useGroupContext() {
  return useOutletContext<GroupContext>();
}

export function GroupDetailLayout() {
  const { groupId } = useParams<{ groupId: UUID }>();
  const { t } = useTranslation();
  const { user, refreshCaps } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);

  const group = useQuery({
    queryKey: groupKeys.detail(groupId!),
    queryFn: () => groupsService.get(groupId!),
    enabled: !!groupId,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: groupKeys.all });
  };

  const removeGroup = useMutation({
    mutationFn: () => groupsService.remove(groupId!),
    onSuccess: async () => {
      await invalidate();
      await refreshCaps();
      navigate("/gruppi/gruppi");
    },
  });

  if (group.isLoading || !groupId) return <Spinner />;
  if (group.isError) {
    // A private group a non-member can't read 404s the same as one that
    // genuinely doesn't exist (backend deliberately doesn't distinguish —
    // see can_read_group), so this stays equally generic rather than
    // claiming "private" for what might just be a bad link.
    return (
      <div className="sf-section__body">
        <BackLink to="/gruppi/gruppi" label={t("gruppi.backToGroups")} />
        <p className="sf-muted">{t("errors.notFound")}</p>
      </div>
    );
  }
  if (!group.data) return null;
  const g = group.data;

  const myRow = g.members?.find((m) => m.user_id === user?.id);
  const isMember = !!myRow;
  const manages = user?.is_superadmin || myRow?.role === "owner" || myRow?.role === "admin";
  const isOwner = user?.is_superadmin || myRow?.role === "owner";
  const memberCount = g.members?.filter((m) => m.status === "active").length;
  const pendingRequests = g.members?.filter((m) => m.status === "requested").length ?? 0;

  const context: GroupContext = { groupId, group: g, isMember, manages, isOwner };

  return (
    <div className="sf-section__body">
      <BackLink to="/gruppi/gruppi" label={t("gruppi.backToGroups")} />
      <Card>
        <div className={entityHeaderStyles.header}>
          <div className={entityHeaderStyles.identity}>
            {g.profile_image && <img className="sf-avatar sf-avatar--lg" src={g.profile_image.url} alt="" />}
            <div>
              <h1 className={entityHeaderStyles.name}>{g.name}</h1>
              {memberCount != null && (
                <p className={`sf-muted ${entityHeaderStyles.meta}`}>
                  {t("gruppi.memberCount", { count: memberCount })}
                </p>
              )}
              <span className="sf-badge">{t(`gruppi.${g.visibility}`)}</span>
            </div>
          </div>
          {isOwner && (
            <div className={entityHeaderStyles.actions}>
              <ImageUploader
                create={() => groupsService.uploadImage(groupId)}
                confirm={(id) => groupsService.confirmImage(groupId, id)}
                onDone={invalidate}
                crop
                icon={<ImagePlus size={16} />}
                label={t("common.upload")}
              />
              <Button
                variant="danger"
                className="sf-btn--icon-sm"
                aria-label={t("common.delete")}
                onClick={() => setDeleting(true)}
              >
                <Trash2 size={16} />
              </Button>
            </div>
          )}
        </div>
      </Card>

      <SectionLayout
        tabs={[
          ...(isMember ? [{ to: `/gruppi/gruppi/${groupId}`, label: t("gruppi.news"), end: true }] : []),
          { to: `/gruppi/gruppi/${groupId}/informazioni`, label: t("gruppi.overview") },
          { to: `/gruppi/gruppi/${groupId}/attivita`, label: t("gruppi.groupActivities") },
          ...(isMember
            ? [{
                to: `/gruppi/gruppi/${groupId}/membri`,
                label: t("gruppi.members"),
                badge: manages ? pendingRequests : 0,
              }]
            : []),
        ]}
        context={context}
        sticky={false}
      />

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

export function GroupFeedRoute() {
  const { groupId, manages } = useGroupContext();
  return <EntityFeed ownerType="group" ownerId={groupId} canManage={manages} />;
}
