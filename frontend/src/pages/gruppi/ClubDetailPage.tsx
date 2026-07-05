import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clubsService, clubKeys } from "@/services/clubs";
import { boatsService, boatKeys } from "@/services/boats";
import { rbacService } from "@/services/rbac";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { UserPicker } from "@/components/common/UserPicker";
import { userLabel } from "@/utils/format";
import { ClubDevices } from "./ClubDevices";
import { ClubRegattas } from "./ClubRegattas";
import type { UUID, UserSummary } from "@/types";

function GrantRoleDialog({ clubId, onClose }: { clubId: UUID; onClose: () => void }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [roleName, setRoleName] = useState("race_officer");
  const roles = useQuery({ queryKey: ["roles"], queryFn: rbacService.roles });

  const grant = useMutation({
    mutationFn: (u: UserSummary) => {
      const role = roles.data?.find((r) => r.name === roleName);
      if (!role) throw new Error("role not loaded");
      return rbacService.grant({ user_id: u.id, role_id: role.id, scope_club_id: clubId });
    },
    onSuccess: () => {
      notify(t("common.saved"), "success");
      onClose();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <Modal title={t("gruppi.grantRole")} onClose={onClose}>
      <Select
        label={t("common.role")}
        id="grant-role"
        value={roleName}
        onChange={(e) => setRoleName(e.target.value)}
      >
        {(roles.data ?? [])
          .filter((r) => r.name !== "superadmin")
          .map((r) => (
            <option key={r.id} value={r.name}>
              {r.name}
            </option>
          ))}
      </Select>
      <UserPicker
        busy={grant.isPending}
        pickLabel={t("gruppi.grantRole")}
        onPick={(u) => grant.mutate(u)}
      />
    </Modal>
  );
}

export function ClubDetailPage() {
  const { clubId } = useParams<{ clubId: UUID }>();
  const { t } = useTranslation();
  const { user } = useAuth();
  const { can, memberOfClub } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const club = useQuery({
    queryKey: clubKeys.detail(clubId!),
    queryFn: () => clubsService.get(clubId!),
    enabled: !!clubId,
  });
  const isMember = !!clubId && (memberOfClub(clubId) || can("club.manage", clubId));
  const members = useQuery({
    queryKey: clubKeys.members(clubId!),
    queryFn: () => clubsService.members(clubId!),
    enabled: !!clubId && isMember,
  });
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });

  const [editing, setEditing] = useState(false);
  const [granting, setGranting] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", city: "", website: "" });

  useEffect(() => {
    if (club.data) {
      setForm({
        name: club.data.name ?? "",
        description: club.data.description ?? "",
        city: club.data.city ?? "",
        website: club.data.website ?? "",
      });
    }
  }, [club.data]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: clubKeys.all });
  };

  const save = useMutation({
    mutationFn: () =>
      clubsService.update(clubId!, {
        name: form.name,
        description: form.description || null,
        city: form.city || null,
        website: form.website || null,
      }),
    onSuccess: async () => {
      setEditing(false);
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const approve = useMutation({
    mutationFn: (userId: UUID) => clubsService.setMemberStatus(clubId!, userId, "active"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clubKeys.members(clubId!) }),
  });
  const removeMember = useMutation({
    mutationFn: (userId: UUID) => clubsService.removeMember(clubId!, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clubKeys.members(clubId!) }),
  });
  const invite = useMutation({
    mutationFn: (userId: UUID) => clubsService.addMember(clubId!, { user_id: userId }),
    onSuccess: async () => {
      setInviting(false);
      await queryClient.invalidateQueries({ queryKey: clubKeys.members(clubId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (club.isLoading || !clubId) return <Spinner />;
  if (!club.data) return null;
  const c = club.data;

  // In-place management (no separate admin page): same URL, extra actions.
  const manages = can("club.manage", clubId);
  const managesMembers = can("user_club.manage", clubId);
  const managesRegattas = can("regatta.manage", clubId);
  const managesRoles = can("user_role.manage_scoped", clubId);
  const stationedBoats = boats.data?.filter((b) => b.club_id === clubId) ?? [];

  return (
    <div className="sf-section__body">
      <Card
        title={
          <>
            {c.logo && <img className="sf-avatar" src={c.logo.url} alt="" />} {c.name}
            {manages && <span className="sf-badge sf-badge--success"> {t("gruppi.manageMode")}</span>}
          </>
        }
        actions={
          manages && (
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <ImageUploader
                create={() => clubsService.uploadLogo(clubId)}
                confirm={(id) => clubsService.confirmLogo(clubId, id)}
                onDone={invalidate}
              />
              <Button variant="ghost" className="sf-btn--sm" onClick={() => setEditing(true)}>
                {t("gruppi.editClub")}
              </Button>
              {managesRoles && (
                <Button variant="ghost" className="sf-btn--sm" onClick={() => setGranting(true)}>
                  {t("gruppi.grantRole")}
                </Button>
              )}
            </span>
          )
        }
      >
        <p className="sf-muted">{c.description}</p>
        <p className="sf-muted">
          {c.city ?? ""}{" "}
          {c.website && (
            <a href={c.website} target="_blank" rel="noreferrer">
              {c.website}
            </a>
          )}
        </p>
      </Card>

      {isMember && (
        <Card
          title={t("gruppi.clubMembers")}
          actions={
            managesMembers && (
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
                  <th>{t("common.status")}</th>
                  {managesMembers && <th />}
                </tr>
              </thead>
              <tbody>
                {members.data
                  ?.filter((m) => m.status !== "deleted")
                  .map((m) => (
                    <tr key={m.user_id}>
                      <td>{userLabel(m.user)}</td>
                      <td>
                        <span
                          className={
                            m.status === "active"
                              ? "sf-badge sf-badge--success"
                              : "sf-badge sf-badge--warning"
                          }
                        >
                          {m.status}
                        </span>
                      </td>
                      {managesMembers && (
                        <td style={{ display: "flex", gap: "0.4rem" }}>
                          {(m.status === "requested" || m.status === "invited") && (
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

      <ClubRegattas clubId={clubId} manage={managesRegattas} />

      {stationedBoats.length > 0 && (
        <Card title={t("gruppi.stationedBoats")}>
          <div className="sf-strip">
            {stationedBoats.map((b) => (
              <div key={b.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{b.name}</strong>{" "}
                  <span className="sf-muted">{b.sail_number ?? ""}</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {manages && <ClubDevices clubId={clubId} />}

      {editing && (
        <Modal title={t("gruppi.editClub")} onClose={() => setEditing(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="ce-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <TextAreaField
              label={t("common.description")}
              id="ce-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <div className="sf-form__row">
              <InputField
                label={t("gruppi.city")}
                id="ce-city"
                value={form.city}
                onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
              />
              <InputField
                label={t("gruppi.website")}
                id="ce-web"
                value={form.website}
                onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
              />
            </div>
            <div className="sf-form__actions">
              <Button type="submit" disabled={save.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {granting && <GrantRoleDialog clubId={clubId} onClose={() => setGranting(false)} />}
      {inviting && (
        <Modal title={t("gruppi.invite")} onClose={() => setInviting(false)}>
          <UserPicker
            busy={invite.isPending}
            pickLabel={t("gruppi.invite")}
            onPick={(u) => invite.mutate(u.id)}
          />
        </Modal>
      )}
    </div>
  );
}
