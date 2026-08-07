import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NotebookText } from "lucide-react";
import { boatsService, boatKeys } from "@/services/boats";
import type { Boat, BoatClass } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Button, ICON_BTN } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ClassPicker } from "@/components/common/ClassPicker";
import styles from "./BoatsPage.module.css";

export function BoatsPage() {
  const { t } = useTranslation();
  const { refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", sail_number: "", boat_class_id: "" });

  const boats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });
  const classes = useQuery({
    queryKey: boatKeys.classes(),
    queryFn: () => boatsService.listClasses({ limit: 1000, sort: "name" }),
  });

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

  const boatClass = (id: string | null) => (id && classes.data?.find((c) => c.id === id)) || null;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <>
      <div className="sf-toolbar" style={{ justifyContent: "flex-end" }}>
        <span style={{ display: "flex", gap: "0.5rem" }}>
          <Link to="/profilo/barche/modelli" className="sf-btn sf-btn--ghost">
            {t("noteTemplates.title")}
          </Link>
          <Button data-tour="profilo-add-boat" onClick={() => setCreating(true)}>{t("boats.addBoat")}</Button>
        </span>
      </div>
      {boats.data?.length === 0 ? (
        <EmptyState>{t("boats.empty")}</EmptyState>
      ) : (
        <>
          <div className="sf-tablewrap sf-desktop-only">
            <table className="sf-table">
              <thead>
                <tr>
                  <th />
                  <th>{t("common.name")}</th>
                  <th>{t("boats.sailNumber")}</th>
                  <th>{t("boats.boatClass")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {boats.data?.map((b) => {
                  const cl = boatClass(b.boat_class_id);
                  const photo = b.photos.find(Boolean);
                  return (
                    <tr key={b.id}>
                      <td>
                        {photo ? (
                          <img className="sf-avatar sf-avatar--sm" src={photo.url} alt="" />
                        ) : (
                          <span className="sf-muted">—</span>
                        )}
                      </td>
                      <td>
                        <Link to={`/profilo/barche/${b.id}`}>{b.name}</Link>
                      </td>
                      <td>{b.sail_number ?? "—"}</td>
                      <td>
                        {cl ? (
                          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            {cl.logo && (
                              <img className="sf-avatar sf-avatar--sm" src={cl.logo.url} alt="" />
                            )}
                            {cl.name}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className={styles.rowNotebook}>
                        <Link
                          to={`/profilo/barche/${b.id}/quaderno`}
                          className={ICON_BTN}
                          aria-label={t("boatNotes.openFor", { name: b.name })}
                          title={t("boatNotes.open")}
                        >
                          <NotebookText size={15} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className={`${styles.cards} sf-mobile-only`}>
            {boats.data?.map((b) => (
              <BoatCard key={b.id} boat={b} boatClass={boatClass(b.boat_class_id)} />
            ))}
          </div>
        </>
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
            <ClassPicker
              label={t("boats.boatClass")}
              id="boat-class"
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
      )}
    </>
  );
}

function BoatCard({ boat, boatClass }: { boat: Boat; boatClass: BoatClass | null }) {
  const { t } = useTranslation();
  const photo = boat.photos.find(Boolean);
  return (
    <div className={`sf-card ${styles.card}`}>
      <div className={styles.cardPhoto}>
        {photo ? (
          <img src={photo.url} alt="" />
        ) : (
          <span className={styles.cardPhotoEmpty}>—</span>
        )}
      </div>
      <div className={styles.cardMain}>
        <Link to={`/profilo/barche/${boat.id}`} className={styles.cardName}>
          {boat.name}
        </Link>
        <div className={styles.cardMeta}>
          <span>{boat.sail_number ?? "—"}</span>
          {boatClass && (
            <>
              <span>·</span>
              {boatClass.logo && <img className={styles.classLogo} src={boatClass.logo.url} alt="" />}
              <span>{boatClass.name}</span>
            </>
          )}
        </div>
      </div>
      <div className={styles.cardNotebook}>
        <Link
          to={`/profilo/barche/${boat.id}/quaderno`}
          className={ICON_BTN}
          aria-label={t("boatNotes.openFor", { name: boat.name })}
          title={t("boatNotes.open")}
        >
          <NotebookText size={15} />
        </Link>
      </div>
    </div>
  );
}
