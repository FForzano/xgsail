import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import { regattasService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { RegattaDivision, UUID } from "@/types";
import styles from "./RegattaDivisions.module.css";

/** Organizer-only management panel for a regatta's scoring divisions
 * (e.g. "Catamarani"/"Derive") — each division independently ranks its own
 * entries in the regatta's standings. Renders nothing when the caller can't
 * manage the regatta; the read-only list lives elsewhere (entries/standings).
 *
 * Bare content: the caller owns the surrounding chrome (a `Modal` on the
 * regatta page), so this never draws a heading or a box of its own. */
export function RegattaDivisions({ regattaId, canManage }: { regattaId: UUID; canManage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const [newName, setNewName] = useState("");
  const [newLaps, setNewLaps] = useState("");
  const [editingId, setEditingId] = useState<UUID | null>(null);
  const [editName, setEditName] = useState("");
  const [editLaps, setEditLaps] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<UUID | null>(null);

  const divisions = useQuery({
    queryKey: raceKeys.divisions(regattaId),
    queryFn: () => regattasService.divisions(regattaId),
    enabled: canManage,
  });

  const invalidateAll = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: raceKeys.divisions(regattaId) }),
      queryClient.invalidateQueries({ queryKey: raceKeys.entries(regattaId) }),
      queryClient.invalidateQueries({ queryKey: raceKeys.standings(regattaId) }),
    ]);

  const notifyError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 409) {
      notify(t("regate.divisionDuplicate"), "error");
    } else {
      notify(t("errors.generic"), "error");
    }
  };

  const create = useMutation({
    mutationFn: () =>
      regattasService.createDivision(regattaId, {
        name: newName.trim(),
        laps: newLaps.trim() ? Number(newLaps) : undefined,
      }),
    onSuccess: async () => {
      setNewName("");
      setNewLaps("");
      await invalidateAll();
    },
    onError: notifyError,
  });

  const update = useMutation({
    mutationFn: ({
      divisionId,
      body,
    }: {
      divisionId: UUID;
      body: { name?: string; sort_order?: number; laps?: number | null };
    }) => regattasService.updateDivision(regattaId, divisionId, body),
    onSuccess: async () => {
      setEditingId(null);
      await invalidateAll();
    },
    onError: notifyError,
  });

  const remove = useMutation({
    mutationFn: (divisionId: UUID) => regattasService.removeDivision(regattaId, divisionId),
    onSuccess: async () => {
      setPendingDeleteId(null);
      await invalidateAll();
    },
    onError: (err: unknown) => {
      setPendingDeleteId(null);
      notifyError(err);
    },
  });

  if (!canManage) return null;

  const rows = divisions.data ?? [];

  const startEdit = (division: RegattaDivision) => {
    setEditingId(division.id);
    setEditName(division.name);
    setEditLaps(division.laps != null ? String(division.laps) : "");
  };

  const saveEdit = (division: RegattaDivision) => {
    const name = editName.trim();
    if (!name) return;
    const laps = editLaps.trim() ? Number(editLaps) : null;
    update.mutate({
      divisionId: division.id,
      body: {
        ...(name !== division.name ? { name } : {}),
        ...(laps !== division.laps ? { laps } : {}),
      },
    });
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = rows[index + direction];
    const current = rows[index];
    if (!target || !current) return;
    update.mutate({ divisionId: current.id, body: { sort_order: target.sort_order } });
    update.mutate({ divisionId: target.id, body: { sort_order: current.sort_order } });
  };

  const pendingDelete = rows.find((d) => d.id === pendingDeleteId) ?? null;

  return (
    <>
      {divisions.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState>{t("regate.divisionsEmpty")}</EmptyState>
      ) : (
        <ul className={styles.list}>
          {rows.map((division, index) => (
            <li key={division.id} className={styles.row}>
              {editingId === division.id ? (
                <form
                  className={`sf-form__row ${styles.editForm}`}
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    saveEdit(division);
                  }}
                >
                  <InputField
                    id={`division-name-${division.id}`}
                    label={t("regate.divisionName")}
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    required
                  />
                  <InputField
                    id={`division-laps-${division.id}`}
                    label={t("regate.divisionLaps")}
                    type="number"
                    min={1}
                    value={editLaps}
                    onChange={(e) => setEditLaps(e.target.value)}
                  />
                  <Button type="submit" disabled={!editName.trim() || update.isPending}>
                    {t("common.save")}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setEditingId(null)}>
                    {t("common.cancel")}
                  </Button>
                </form>
              ) : (
                <>
                  <span className={styles.order}>
                    <button
                      type="button"
                      className={styles.moveButton}
                      aria-label={t("common.sortOrder")}
                      disabled={index === 0 || update.isPending}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      type="button"
                      className={styles.moveButton}
                      aria-label={t("common.sortOrder")}
                      disabled={index === rows.length - 1 || update.isPending}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown size={14} />
                    </button>
                  </span>
                  <button
                    type="button"
                    className={styles.name}
                    onClick={() => startEdit(division)}
                    title={t("common.edit")}
                  >
                    {division.name}
                  </button>
                  {division.laps != null && (
                    <span className="sf-badge sf-badge--sm">
                      {division.laps} {t("regate.divisionLaps").toLowerCase()}
                    </span>
                  )}
                  {division.entry_count != null && (
                    <span className={`sf-muted ${styles.count}`}>
                      {t("regate.divisionEntryCount", { count: division.entry_count })}
                    </span>
                  )}
                  <button
                    type="button"
                    className={styles.deleteButton}
                    aria-label={t("regate.deleteDivision")}
                    title={t("regate.deleteDivision")}
                    onClick={() => setPendingDeleteId(division.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      <form
        className={`sf-form__row ${styles.addForm}`}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (newName.trim()) create.mutate();
        }}
      >
        <InputField
          id="new-division-name"
          label={t("regate.newDivision")}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          required
        />
        <InputField
          id="new-division-laps"
          label={t("regate.divisionLaps")}
          type="number"
          min={1}
          value={newLaps}
          onChange={(e) => setNewLaps(e.target.value)}
        />
        <Button type="submit" disabled={!newName.trim() || create.isPending}>
          {t("common.add")}
        </Button>
      </form>

      {pendingDelete && (
        <ConfirmDialog
          title={t("regate.deleteDivision")}
          message={t("regate.confirmDeleteDivision")}
          confirmLabel={t("common.delete")}
          busy={remove.isPending}
          onClose={() => setPendingDeleteId(null)}
          onConfirm={() => remove.mutate(pendingDelete.id)}
        />
      )}
    </>
  );
}
