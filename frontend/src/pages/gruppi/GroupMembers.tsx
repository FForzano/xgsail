import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, LogOut, Search, UserMinus, UserPlus } from "lucide-react";
import { groupsService, groupKeys } from "@/services/groups";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Avatar } from "@/components/ui/Avatar";
import { UserPicker } from "@/components/common/UserPicker";
import { userLabel } from "@/utils/format";
import { smartSearch } from "@/utils/smartSearch";
import { useGroupContext } from "./GroupDetailLayout";
import type { GroupMember, GroupRole, UUID } from "@/types";

export function GroupMembers() {
  const { groupId, group, isOwner, manages } = useGroupContext();
  const { t } = useTranslation();
  const { user, refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [inviting, setInviting] = useState(false);
  const [query, setQuery] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: groupKeys.all });
  };

  const invite = useMutation({
    mutationFn: (userId: UUID) => groupsService.addMember(groupId, { user_id: userId }),
    onSuccess: async () => {
      setInviting(false);
      notify(t("gruppi.joinRequested"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: UUID; role: GroupRole }) =>
      groupsService.updateMember(groupId, userId, { role }),
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const approve = useMutation({
    mutationFn: (userId: UUID) => groupsService.updateMember(groupId, userId, { status: "active" }),
    onSuccess: invalidate,
  });
  const removeMember = useMutation({
    mutationFn: (userId: UUID) => groupsService.removeMember(groupId, userId),
    onSuccess: async () => {
      await invalidate();
      await refreshCaps();
    },
  });

  if (!group.members) return null;

  const members = group.members;
  const pendingCount = members.filter((m) => m.status === "requested").length;
  const filtered = pendingOnly ? members.filter((m) => m.status === "requested") : members;
  const showSearch = members.length > 6;
  const visible: GroupMember[] = showSearch ? smartSearch(query, filtered, (m) => [userLabel(m.user)]) : filtered;

  return (
    <Card
      title={t("gruppi.members")}
      actions={
        manages && (
          <span style={{ display: "flex", gap: "0.5rem" }}>
            {pendingCount > 0 && (
              <Button
                variant={pendingOnly ? "primary" : "ghost"}
                className="sf-btn--sm"
                aria-pressed={pendingOnly}
                onClick={() => setPendingOnly((v) => !v)}
              >
                {t("gruppi.pendingOnly")} ({pendingCount})
              </Button>
            )}
            <Button
              variant="ghost"
              className="sf-btn--icon-sm"
              aria-label={t("gruppi.invite")}
              onClick={() => setInviting(true)}
            >
              <UserPlus size={16} />
            </Button>
          </span>
        )
      }
    >
      {showSearch && (
        <div className="sf-entity-search" style={{ marginBottom: "0.75rem" }}>
          <Search size={16} className="sf-entity-search__icon" />
          <input
            className="sf-entity-search__input"
            type="search"
            placeholder={t("common.search")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th>{t("common.name")}</th>
              <th>{t("common.role")}</th>
              {manages && <th />}
            </tr>
          </thead>
          <tbody>
            {visible.map((m) => (
              <tr key={m.user_id} className={m.status !== "active" ? "sf-row--pending" : undefined}>
                <td>
                  <div className="sf-crew-row">
                    <Avatar
                      size="sm"
                      profileImage={m.user?.profile_image}
                      firstName={m.user?.first_name}
                      lastName={m.user?.last_name}
                    />
                    <div>
                      <div>{userLabel(m.user)}</div>
                      {m.status !== "active" && (
                        <span className="sf-badge sf-badge--warning sf-badge--sm">{m.status}</span>
                      )}
                    </div>
                  </div>
                </td>
                <td>
                  {isOwner && m.status === "active" && m.user_id !== user?.id ? (
                    <select
                      className="sf-field__input sf-select sf-select--sm"
                      aria-label={t("common.role")}
                      value={m.role}
                      onChange={(e) => setRole.mutate({ userId: m.user_id, role: e.target.value as GroupRole })}
                    >
                      {(["owner", "admin", "member"] as GroupRole[]).map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  ) : (
                    m.role
                  )}
                </td>
                {manages && (
                  <td className="sf-row-actions">
                    {m.status === "requested" && (
                      <Button
                        className="sf-btn--icon-sm"
                        aria-label={t("gruppi.approve")}
                        onClick={() => approve.mutate(m.user_id)}
                      >
                        <Check size={16} />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      className="sf-btn--icon-sm"
                      aria-label={m.user_id === user?.id ? t("gruppi.leave") : t("common.remove")}
                      onClick={() => removeMember.mutate(m.user_id)}
                    >
                      {m.user_id === user?.id ? <LogOut size={16} /> : <UserMinus size={16} />}
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {inviting && (
        <Modal title={t("gruppi.invite")} onClose={() => setInviting(false)}>
          <UserPicker busy={invite.isPending} pickLabel={t("gruppi.invite")} onPick={(u) => invite.mutate(u.id)} />
        </Modal>
      )}
    </Card>
  );
}
