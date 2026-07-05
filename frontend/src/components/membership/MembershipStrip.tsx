import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authService } from "@/services/auth";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import type { UUID } from "@/types";

export const membershipKeys = { mine: ["memberships", "me"] as const };

// Shared top strip of the Gruppi section: pending invites (accept/decline)
// and my join requests (cancel). Discovery lives in the list pages below.
export function MembershipStrip() {
  const { t } = useTranslation();
  const { user, refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const memberships = useQuery({
    queryKey: membershipKeys.mine,
    queryFn: authService.myMemberships,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: membershipKeys.mine });
    await queryClient.invalidateQueries({ queryKey: clubKeys.all });
    await queryClient.invalidateQueries({ queryKey: groupKeys.all });
    await refreshCaps();
  };

  const acceptClub = useMutation({
    mutationFn: (clubId: UUID) => clubsService.setMemberStatus(clubId, user!.id, "active"),
    onSuccess: async () => {
      notify(t("memberships.accepted"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const declineClub = useMutation({
    mutationFn: (clubId: UUID) => clubsService.removeMember(clubId, user!.id),
    onSuccess: invalidate,
  });
  const acceptGroup = useMutation({
    mutationFn: (groupId: UUID) => groupsService.updateMember(groupId, user!.id, { status: "active" }),
    onSuccess: async () => {
      notify(t("memberships.accepted"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const declineGroup = useMutation({
    mutationFn: (groupId: UUID) => groupsService.removeMember(groupId, user!.id),
    onSuccess: invalidate,
  });

  const data = memberships.data;
  if (!data) return null;

  const clubInvites = data.clubs.filter((c) => c.status === "invited");
  const groupInvites = data.groups.filter((g) => g.status === "invited");
  const requests = [
    ...data.clubs
      .filter((c) => c.status === "requested")
      .map((c) => ({ kind: "club" as const, id: c.club_id, name: c.name })),
    ...data.groups
      .filter((g) => g.status === "requested")
      .map((g) => ({ kind: "group" as const, id: g.group_id, name: g.name })),
  ];

  if (clubInvites.length + groupInvites.length + requests.length === 0) return null;

  return (
    <div className="sf-strip">
      {clubInvites.map((c) => (
        <div key={c.club_id} className="sf-strip__item">
          <span>
            {t("memberships.clubInvite")} <strong>{c.name}</strong>
          </span>
          <span className="sf-strip__actions">
            <Button
              className="sf-btn--sm"
              onClick={() => acceptClub.mutate(c.club_id)}
              disabled={acceptClub.isPending}
            >
              {t("memberships.accept")}
            </Button>
            <Button
              variant="ghost"
              className="sf-btn--sm"
              onClick={() => declineClub.mutate(c.club_id)}
            >
              {t("memberships.decline")}
            </Button>
          </span>
        </div>
      ))}
      {groupInvites.map((g) => (
        <div key={g.group_id} className="sf-strip__item">
          <span>
            {t("memberships.groupInvite")} <strong>{g.name}</strong>
          </span>
          <span className="sf-strip__actions">
            <Button
              className="sf-btn--sm"
              onClick={() => acceptGroup.mutate(g.group_id)}
              disabled={acceptGroup.isPending}
            >
              {t("memberships.accept")}
            </Button>
            <Button
              variant="ghost"
              className="sf-btn--sm"
              onClick={() => declineGroup.mutate(g.group_id)}
            >
              {t("memberships.decline")}
            </Button>
          </span>
        </div>
      ))}
      {requests.map((r) => (
        <div key={`${r.kind}-${r.id}`} className="sf-strip__item sf-strip__item--muted">
          <span>
            {t("memberships.requestPending")} <strong>{r.name}</strong>
          </span>
          <Button
            variant="ghost"
            className="sf-btn--sm"
            onClick={() =>
              r.kind === "club" ? declineClub.mutate(r.id) : declineGroup.mutate(r.id)
            }
          >
            {t("memberships.cancelRequest")}
          </Button>
        </div>
      ))}
    </div>
  );
}
