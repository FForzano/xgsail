import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { groupsService, groupKeys } from "@/services/groups";
import { membershipKeys } from "@/components/membership/MembershipStrip";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import type { UUID } from "@/types";

export function GroupsPage() {
  const { t } = useTranslation();
  const { memberOfGroup } = useCapabilities();
  const { refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", visibility: "private" });

  // One call: public groups + mine; split via capabilities memberships.
  const groups = useQuery({ queryKey: groupKeys.all, queryFn: () => groupsService.list() });

  const create = useMutation({
    mutationFn: () =>
      groupsService.create({
        name: form.name,
        description: form.description || null,
        visibility: form.visibility as "public" | "private",
      }),
    onSuccess: async () => {
      setCreating(false);
      setForm({ name: "", description: "", visibility: "private" });
      await queryClient.invalidateQueries({ queryKey: groupKeys.all });
      await refreshCaps();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const join = useMutation({
    mutationFn: (groupId: UUID) => groupsService.addMember(groupId),
    onSuccess: async () => {
      notify(t("gruppi.joinRequested"), "success");
      await queryClient.invalidateQueries({ queryKey: membershipKeys.mine });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (groups.isLoading) return <Spinner />;

  const mine = groups.data?.filter((g) => memberOfGroup(g.id)) ?? [];
  const discover = groups.data?.filter((g) => !memberOfGroup(g.id)) ?? [];

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <>
      <Card
        title={t("gruppi.myGroups")}
        actions={<Button onClick={() => setCreating(true)}>{t("gruppi.createGroup")}</Button>}
      >
        {mine.length === 0 ? (
          <EmptyState>{t("gruppi.emptyGroups")}</EmptyState>
        ) : (
          <div className="sf-grid">
            {mine.map((g) => (
              <Link key={g.id} to={`/gruppi/gruppi/${g.id}`} className="sf-card">
                {g.profile_image && <img className="sf-avatar" src={g.profile_image.url} alt="" />}
                <h3>{g.name}</h3>
                <p className="sf-muted">{g.description}</p>
                <span className="sf-badge">{t(`gruppi.${g.visibility}`)}</span>
              </Link>
            ))}
          </div>
        )}
      </Card>

      {discover.length > 0 && (
        <Card title={t("gruppi.discoverGroups")}>
          <div className="sf-strip">
            {discover.map((g) => (
              <div key={g.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{g.name}</strong>{" "}
                  <span className="sf-muted">{g.description}</span>
                </span>
                <Button
                  className="sf-btn--sm"
                  disabled={join.isPending}
                  onClick={() => join.mutate(g.id)}
                >
                  {t("gruppi.join")}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {creating && (
        <Modal title={t("gruppi.createGroup")} onClose={() => setCreating(false)}>
          <form onSubmit={onSubmit}>
            <InputField
              label={t("common.name")}
              id="g-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <TextAreaField
              label={t("common.description")}
              id="g-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <Select
              label={t("gruppi.visibility")}
              id="g-vis"
              value={form.visibility}
              onChange={(e) => setForm((f) => ({ ...f, visibility: e.target.value }))}
            >
              <option value="private">{t("gruppi.private")}</option>
              <option value="public">{t("gruppi.public")}</option>
            </Select>
            <div className="sf-form__actions">
              <Button type="submit" disabled={create.isPending || !form.name}>
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
