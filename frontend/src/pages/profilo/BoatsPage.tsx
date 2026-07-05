import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export function BoatsPage() {
  const { t } = useTranslation();
  const { refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", sail_number: "", boat_class_id: "" });

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });
  const classes = useQuery({ queryKey: boatKeys.classes, queryFn: boatsService.listClasses });

  const create = useMutation({
    mutationFn: () =>
      boatsService.create({
        name: form.name,
        sail_number: form.sail_number || null,
        boat_class_id: form.boat_class_id || null,
      }),
    onSuccess: async () => {
      setCreating(false);
      setForm({ name: "", sail_number: "", boat_class_id: "" });
      await queryClient.invalidateQueries({ queryKey: boatKeys.all });
      await refreshCaps(); // creator became boat owner
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (boats.isLoading) return <Spinner />;

  const className = (id: string | null) =>
    (id && classes.data?.find((c) => c.id === id)?.name) || "—";

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <Card
      title={t("boats.title")}
      actions={<Button onClick={() => setCreating(true)}>{t("boats.addBoat")}</Button>}
    >
      {boats.data?.length === 0 ? (
        <EmptyState>{t("boats.empty")}</EmptyState>
      ) : (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("common.name")}</th>
                <th>{t("boats.sailNumber")}</th>
                <th>{t("boats.boatClass")}</th>
              </tr>
            </thead>
            <tbody>
              {boats.data?.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link to={`/profilo/barche/${b.id}`}>{b.name}</Link>
                  </td>
                  <td>{b.sail_number ?? "—"}</td>
                  <td>{className(b.boat_class_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <Modal title={t("boats.addBoat")} onClose={() => setCreating(false)}>
          <form onSubmit={onSubmit}>
            <InputField
              label={t("common.name")}
              id="boat-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <InputField
              label={t("boats.sailNumber")}
              id="boat-sail"
              value={form.sail_number}
              onChange={(e) => setForm((f) => ({ ...f, sail_number: e.target.value }))}
            />
            <Select
              label={t("boats.boatClass")}
              id="boat-class"
              value={form.boat_class_id}
              onChange={(e) => setForm((f) => ({ ...f, boat_class_id: e.target.value }))}
            >
              <option value="">—</option>
              {classes.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
            <div className="sf-form__actions">
              <Button type="submit" disabled={create.isPending || !form.name}>
                {t("common.create")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}
