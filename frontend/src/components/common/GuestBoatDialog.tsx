import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import type { Boat } from "@/types";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { ClassPicker } from "@/components/common/ClassPicker";

/** Inline "add a boat that isn't yours" form, opened from any boat picker
 * (Registra, Import, regatta join). Creates an ordinary boat flagged
 * `is_guest` — the sailor becomes its owner like any boat they create, and
 * the real owner can later claim it (see `boats.ts`'s claim bindings). */
export function GuestBoatDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (boat: Boat) => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", sail_number: "", boat_class_id: "" });

  const classes = useQuery({
    queryKey: boatKeys.classes(),
    queryFn: () => boatsService.listClasses({ limit: 1000, sort: "name" }),
    enabled: open,
  });

  const create = useMutation({
    mutationFn: () =>
      boatsService.create({
        name: form.name,
        sail_number: form.sail_number || null,
        boat_class_id: form.boat_class_id || null,
        is_guest: true,
      }),
    onSuccess: async (boat) => {
      setForm({ name: "", sail_number: "", boat_class_id: "" });
      await queryClient.invalidateQueries({ queryKey: boatKeys.mine });
      notify(t("boats.guestCreated"), "success");
      onCreated(boat);
    },
    onError: () => notify(t("boats.guestCreateFailed"), "error"),
  });

  if (!open) return null;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <Modal title={t("boats.addGuestBoat")} onClose={onClose}>
      <p className="sf-muted">{t("boats.guestHint")}</p>
      <form onSubmit={onSubmit}>
        <InputField
          label={t("common.name")}
          id="guest-boat-name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          required
        />
        <InputField
          label={t("boats.sailNumber")}
          id="guest-boat-sail"
          value={form.sail_number}
          onChange={(e) => setForm((f) => ({ ...f, sail_number: e.target.value }))}
        />
        <ClassPicker
          label={t("boats.boatClass")}
          id="guest-boat-class"
          classes={classes.data ?? []}
          value={form.boat_class_id}
          onChange={(id) => setForm((f) => ({ ...f, boat_class_id: id }))}
        />
        <div className="sf-form__actions">
          <Button type="submit" disabled={create.isPending || !form.name}>
            {t("common.create")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
