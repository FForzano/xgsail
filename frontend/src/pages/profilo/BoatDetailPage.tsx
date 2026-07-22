import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImageUploader } from "@/components/common/ImageUploader";
import { ClassPicker, ClassInfo } from "@/components/common/ClassPicker";
import { UserPicker } from "@/components/common/UserPicker";
import { AddDeviceDialog } from "@/components/common/AddDeviceDialog";
import { useMediaUpload } from "@/hooks/useMediaUpload";
import { userLabel } from "@/utils/format";
import type { BoatRole, UUID } from "@/types";
import { useRef } from "react";
import photoGridStyles from "@/components/common/photoGrid.module.css";

const BOAT_ROLES: BoatRole[] = ["owner", "admin", "visitor"];
const SAILING_ROLES = ["skipper", "crew"];

function DocumentUpload({
  label,
  current,
  create,
  remove,
  onDone,
}: {
  label: string;
  current: { url: string } | null | undefined;
  create: () => Promise<{ file_id: UUID; upload_url: string }>;
  remove: () => Promise<unknown>;
  onDone: () => Promise<void>;
}) {
  const { t } = useTranslation();
  // Documents (PDF) have no confirm endpoint mismatch: cert/mbsa reuse the
  // generic file flow, confirm happens implicitly on next read — the backend
  // links the file row on presign, so we just PUT and refresh.
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, busy, error } = useMediaUpload({
    create,
    confirm: async () => undefined,
    onDone,
  });
  const removeMutation = useMutation({ mutationFn: remove, onSuccess: onDone });

  return (
    <div className="sf-strip__item sf-strip__item--muted">
      <span>
        {label}
        {error && <span className="sf-form__error"> {error}</span>}
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
          e.target.value = "";
        }}
      />
      <span style={{ display: "flex", gap: "0.4rem" }}>
        <Button
          variant="ghost"
          className="sf-btn--sm"
          disabled={!current}
          aria-label={t("boats.viewDocument")}
          title={t("boats.viewDocument")}
          onClick={() => current && window.open(current.url, "_blank", "noreferrer")}
        >
          ↗
        </Button>
        <Button
          variant="ghost"
          className="sf-btn--sm"
          disabled={busy}
          aria-label={current ? t("common.edit") : t("common.upload")}
          title={current ? t("common.edit") : t("common.upload")}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? "…" : current ? "✎" : "⬆"}
        </Button>
        <Button
          variant="danger"
          className="sf-btn--sm"
          disabled={!current || removeMutation.isPending}
          aria-label={t("common.delete")}
          title={t("common.delete")}
          onClick={() => removeMutation.mutate()}
        >
          ×
        </Button>
      </span>
    </div>
  );
}

export function BoatDetailPage() {
  const { boatId } = useParams<{ boatId: UUID }>();
  const { t } = useTranslation();
  const { refreshCaps } = useAuth();
  const { isBoatManager, isBoatOwner } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const boat = useQuery({
    queryKey: boatKeys.detail(boatId!),
    queryFn: () => boatsService.get(boatId!),
    enabled: !!boatId,
  });
  const members = useQuery({
    queryKey: boatKeys.members(boatId!),
    queryFn: () => boatsService.members(boatId!),
    enabled: !!boatId && isBoatManager(boatId!),
  });

  const classes = useQuery({
    queryKey: boatKeys.classes(),
    queryFn: () => boatsService.listClasses({ limit: 1000, sort: "name" }),
  });
  const [form, setForm] = useState({ name: "", sail_number: "", boat_class_id: "", notes: "" });
  const [inviting, setInviting] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (boat.data) {
      setForm({
        name: boat.data.name ?? "",
        sail_number: boat.data.sail_number ?? "",
        boat_class_id: boat.data.boat_class_id ?? "",
        notes: boat.data.notes ?? "",
      });
    }
  }, [boat.data]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: boatKeys.all });

  const save = useMutation({
    mutationFn: () =>
      boatsService.update(boatId!, {
        name: form.name,
        sail_number: form.sail_number || null,
        boat_class_id: form.boat_class_id || null,
        notes: form.notes || null,
      }),
    onSuccess: async () => {
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const addMember = useMutation({
    mutationFn: (userId: UUID) => boatsService.addMember(boatId!, { user_id: userId, role: "visitor" }),
    onSuccess: async () => {
      setInviting(false);
      await queryClient.invalidateQueries({ queryKey: boatKeys.members(boatId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: UUID; role: BoatRole }) =>
      boatsService.setMemberRole(boatId!, userId, role),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: boatKeys.members(boatId!) });
      await refreshCaps();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const setSailingRole = useMutation({
    mutationFn: ({ userId, sailingRole }: { userId: UUID; sailingRole: string }) =>
      boatsService.setMemberSailingRole(boatId!, userId, sailingRole),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: boatKeys.members(boatId!) }),
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeMember = useMutation({
    mutationFn: (userId: UUID) => boatsService.removeMember(boatId!, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: boatKeys.members(boatId!) });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removeBoat = useMutation({
    mutationFn: () => boatsService.remove(boatId!),
    onSuccess: async () => {
      await invalidate();
      await refreshCaps();
      navigate("/profilo/barche");
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const removePhoto = useMutation({
    mutationFn: (imageId: UUID) => boatsService.removePhoto(boatId!, imageId),
    onSuccess: invalidate,
  });

  if (boat.isLoading || !boatId) return <Spinner />;
  if (!boat.data) return null;

  const manager = isBoatManager(boatId);
  const owner = isBoatOwner(boatId);
  const ownerCount = members.data?.filter((m) => m.role === "owner").length ?? 0;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <div className="sf-section__body">
      <Card
        title={boat.data.name}
        actions={
          owner && (
            <Button variant="danger" className="sf-btn--sm" onClick={() => setDeleting(true)}>
              {t("common.delete")}
            </Button>
          )
        }
      >
        {manager ? (
          <form onSubmit={onSubmit}>
            <div className="sf-form__row">
              <InputField
                label={t("common.name")}
                id="b-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
              <InputField
                label={t("boats.sailNumber")}
                id="b-sail"
                value={form.sail_number}
                onChange={(e) => setForm((f) => ({ ...f, sail_number: e.target.value }))}
              />
              <ClassPicker
                label={t("boats.boatClass")}
                id="b-class"
                classes={classes.data ?? []}
                value={form.boat_class_id as UUID | ""}
                onChange={(id) => setForm((f) => ({ ...f, boat_class_id: id }))}
              />
            </div>
            <InputField
              label={t("boats.notes")}
              id="b-notes"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
            <div className="sf-form__actions">
              <Button type="submit" disabled={save.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className="sf-muted">
              {boat.data.sail_number ?? ""}{" "}
              {classes.data?.find((cl) => cl.id === boat.data?.boat_class_id)?.name ?? ""}
            </p>
            {(() => {
              const cl = classes.data?.find((c) => c.id === boat.data?.boat_class_id);
              return cl ? <ClassInfo boatClass={cl} /> : null;
            })()}
          </>
        )}

        {manager && (
          <div style={{ marginTop: "1rem" }}>
            <DocumentUpload
              label={t("boats.cert")}
              current={boat.data.cert}
              create={() => boatsService.uploadCert(boatId)}
              remove={() => boatsService.removeCert(boatId)}
              onDone={async () => {
                await invalidate();
              }}
            />
            <DocumentUpload
              label={t("boats.mbsa")}
              current={boat.data.mbsa}
              create={() => boatsService.uploadMbsa(boatId)}
              remove={() => boatsService.removeMbsa(boatId)}
              onDone={async () => {
                await invalidate();
              }}
            />
          </div>
        )}
      </Card>

      <Card
        title={t("boats.photos")}
        actions={
          manager && (
            <ImageUploader
              create={() => boatsService.createPhoto(boatId)}
              confirm={(imageId) => boatsService.confirmPhoto(boatId, imageId)}
              onDone={async () => {
                await invalidate();
              }}
            />
          )
        }
      >
        {boat.data.photos.filter(Boolean).length === 0 ? (
          <p className="sf-muted">{t("common.none")}</p>
        ) : (
          <div className={photoGridStyles.grid}>
            {boat.data.photos.map(
              (p) =>
                p && (
                  <figure key={p.image_id}>
                    <img src={p.url} alt="" />
                    {manager && (
                      <Button
                        variant="danger"
                        className={`sf-btn--sm ${photoGridStyles.del}`}
                        onClick={() => removePhoto.mutate(p.image_id)}
                      >
                        ×
                      </Button>
                    )}
                  </figure>
                ),
            )}
          </div>
        )}
      </Card>

      {manager && (
        <Card
          title={t("boats.members")}
          actions={
            <span style={{ display: "flex", gap: "0.5rem" }}>
              <Button variant="ghost" className="sf-btn--sm" onClick={() => setClaiming(true)}>
                {t("devices.claim")}
              </Button>
              <Button className="sf-btn--sm" onClick={() => setInviting(true)}>
                {t("boats.addMember")}
              </Button>
            </span>
          }
        >
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th>{t("common.name")}</th>
                  <th>{t("common.role")}</th>
                  <th>{t("boats.sailingRole")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {members.data?.map((m) => (
                  <tr key={m.user_id}>
                    <td>{userLabel(m.user)}</td>
                    <td>
                      {owner ? (
                        <Select
                          label=""
                          id={`role-${m.user_id}`}
                          value={m.role}
                          onChange={(e) =>
                            setRole.mutate({ userId: m.user_id, role: e.target.value as BoatRole })
                          }
                        >
                          {BOAT_ROLES.map((r) => (
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
                      {owner ? (
                        <Select
                          label=""
                          id={`sailing-role-${m.user_id}`}
                          value={m.default_sailing_role ?? ""}
                          onChange={(e) => {
                            // Clearing back to "—" isn't supported by the backend yet
                            // (PATCH only sets, it can't null the field out) — ignore.
                            if (e.target.value) {
                              setSailingRole.mutate({ userId: m.user_id, sailingRole: e.target.value });
                            }
                          }}
                        >
                          <option value="">—</option>
                          {SAILING_ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        m.default_sailing_role ?? "—"
                      )}
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        disabled={m.role === "owner" && ownerCount <= 1}
                        title={
                          m.role === "owner" && ownerCount <= 1
                            ? t("boats.lastOwner")
                            : undefined
                        }
                        onClick={() => removeMember.mutate(m.user_id)}
                      >
                        {t("common.remove")}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {inviting && (
        <Modal title={t("boats.addMember")} onClose={() => setInviting(false)}>
          <UserPicker busy={addMember.isPending} onPick={(u) => addMember.mutate(u.id)} />
        </Modal>
      )}
      {claiming && (
        <AddDeviceDialog owner={{ owner_boat_id: boatId }} onClose={() => setClaiming(false)} />
      )}
      {deleting && (
        <ConfirmDialog
          title={t("common.delete")}
          message={t("boats.deleteConfirm")}
          busy={removeBoat.isPending}
          onConfirm={() => removeBoat.mutate()}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
