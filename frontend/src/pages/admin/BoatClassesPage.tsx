import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boatsService, boatKeys, type BoatClassSort, type SortOrder } from "@/services/boats";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { RichTextField } from "@/components/ui/RichTextField";
import { Modal } from "@/components/ui/Modal";
import { ImageUploader } from "@/components/common/ImageUploader";
import type { BoatClass, HullType, RigType, SpinnakerType, UUID } from "@/types";

const CLASS_PAGE_SIZE = 20;

const emptyClassForm = {
  name: "",
  description: "",
  loa_m: "",
  beam_m: "",
  sail_area_sqm: "",
  crew_size: "",
  hull_type: "",
  rig_type: "",
  spinnaker_type: "",
  py_rating: "",
  rya_class_id: "",
};

export function BoatClassesPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [hullFilter, setHullFilter] = useState<HullType | "">("");
  const [sort, setSort] = useState<BoatClassSort>("name");
  const [order, setOrder] = useState<SortOrder>("asc");
  const [editing, setEditing] = useState<BoatClass | null>(null);
  const [form, setForm] = useState(emptyClassForm);

  const classes = useQuery({
    queryKey: boatKeys.classes(page, search, hullFilter, sort, order),
    queryFn: () =>
      boatsService.listClasses({
        limit: CLASS_PAGE_SIZE,
        offset: page * CLASS_PAGE_SIZE,
        search: search || undefined,
        hullType: hullFilter,
        sort,
        order,
      }),
  });

  useEffect(() => {
    if (editing) {
      setForm({
        name: editing.name ?? "",
        description: editing.description ?? "",
        loa_m: editing.loa_m?.toString() ?? "",
        beam_m: editing.beam_m?.toString() ?? "",
        sail_area_sqm: editing.sail_area_sqm?.toString() ?? "",
        crew_size: editing.crew_size?.toString() ?? "",
        hull_type: editing.hull_type ?? "",
        rig_type: editing.rig_type ?? "",
        spinnaker_type: editing.spinnaker_type ?? "",
        py_rating: editing.py_rating?.toString() ?? "",
        rya_class_id: editing.rya_class_id?.toString() ?? "",
      });
    }
  }, [editing]);

  // Keep the open edit modal's logo preview in sync after an upload
  // triggers a list refetch (the modal doesn't re-fetch its own copy).
  useEffect(() => {
    if (editing && classes.data) {
      const fresh = classes.data.find((c) => c.id === editing.id);
      if (fresh && fresh.logo !== editing.logo) setEditing(fresh);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classes.data]);

  // Prefix match invalidates every page ([boat-classes, page] for each page).
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["boat-classes"] });

  const create = useMutation({
    mutationFn: () => boatsService.createClass({ name }),
    onSuccess: async () => {
      setName("");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const save = useMutation({
    mutationFn: () =>
      boatsService.updateClass(editing!.id, {
        name: form.name,
        description: form.description || null,
        loa_m: form.loa_m ? Number(form.loa_m) : null,
        beam_m: form.beam_m ? Number(form.beam_m) : null,
        sail_area_sqm: form.sail_area_sqm ? Number(form.sail_area_sqm) : null,
        crew_size: form.crew_size ? Number(form.crew_size) : null,
        hull_type: (form.hull_type || null) as HullType | null,
        rig_type: (form.rig_type || null) as RigType | null,
        spinnaker_type: (form.spinnaker_type || null) as SpinnakerType | null,
        py_rating: form.py_rating ? Math.round(Number(form.py_rating)) : null,
        rya_class_id: form.rya_class_id ? Math.round(Number(form.rya_class_id)) : null,
      }),
    onSuccess: async () => {
      setEditing(null);
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => boatsService.removeClass(id),
    onSuccess: () => invalidate(),
    onError: () => notify(t("errors.generic"), "error"),
  });

  return (
    <>
      <div className="sf-form__row" style={{ alignItems: "end" }}>
        <InputField
          label={t("common.search")}
          id="bc-search"
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          placeholder={t("admin.boatClasses")}
        />
        <Select
          label={t("admin.hullType")}
          id="bc-hull-filter"
          value={hullFilter}
          onChange={(e) => {
            setHullFilter(e.target.value as HullType | "");
            setPage(0);
          }}
        >
          <option value="">{t("admin.allHullTypes")}</option>
          <option value="monohull">{t("admin.monohull")}</option>
          <option value="multihull">{t("admin.multihull")}</option>
        </Select>
        <Select
          label={t("common.sortBy")}
          id="bc-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as BoatClassSort)}
        >
          <option value="name">{t("common.name")}</option>
          <option value="py_rating">{t("admin.pyRating")}</option>
          <option value="crew_size">{t("admin.crewSize")}</option>
          <option value="rya_class_id">{t("admin.ryaClassId")}</option>
        </Select>
        <Select
          label={t("common.sortOrder")}
          id="bc-order"
          value={order}
          onChange={(e) => setOrder(e.target.value as SortOrder)}
        >
          <option value="asc">{t("common.ascending")}</option>
          <option value="desc">{t("common.descending")}</option>
        </Select>
      </div>
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th />
              <th>{t("common.name")}</th>
              <th>{t("admin.hullType")}</th>
              <th>{t("admin.loa")}</th>
              <th>{t("admin.sailArea")}</th>
              <th>{t("admin.crewSize")}</th>
              <th>{t("admin.rigType")}</th>
              <th>{t("admin.spinnakerType")}</th>
              <th>{t("admin.pyRating")}</th>
              <th>{t("admin.ryaClassId")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {classes.data?.map((c) => (
              <tr key={c.id}>
                <td>
                  {c.logo ? (
                    <img className="sf-avatar sf-avatar--sm" src={c.logo.url} alt="" />
                  ) : (
                    <span className="sf-muted">—</span>
                  )}
                </td>
                <td>
                  <strong>{c.name}</strong>
                </td>
                <td>{c.hull_type ? t(`admin.${c.hull_type}`) : "—"}</td>
                <td>{c.loa_m ?? "—"}</td>
                <td>{c.sail_area_sqm ?? "—"}</td>
                <td>{c.crew_size ?? "—"}</td>
                <td>{c.rig_type ? t(`admin.${c.rig_type}`) : "—"}</td>
                <td>{c.spinnaker_type ? t(`admin.spinnaker_${c.spinnaker_type}`) : "—"}</td>
                <td>{c.py_rating ?? "—"}</td>
                <td>{c.rya_class_id ?? "—"}</td>
                <td>
                  <span style={{ display: "flex", gap: "0.4rem" }}>
                    <Button
                      variant="ghost"
                      className="sf-btn--sm"
                      aria-label={t("common.edit")}
                      title={t("common.edit")}
                      onClick={() => setEditing(c)}
                    >
                      ✎
                    </Button>
                    <Button
                      variant="danger"
                      className="sf-btn--sm"
                      aria-label={t("common.delete")}
                      title={t("common.delete")}
                      onClick={() => remove.mutate(c.id)}
                    >
                      ×
                    </Button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="sf-form__actions" style={{ justifyContent: "flex-start" }}>
        <Button
          variant="ghost"
          className="sf-btn--sm"
          disabled={page === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          ‹
        </Button>
        <Button
          variant="ghost"
          className="sf-btn--sm"
          disabled={(classes.data?.length ?? 0) < CLASS_PAGE_SIZE}
          onClick={() => setPage((p) => p + 1)}
        >
          ›
        </Button>
      </div>

      <form
        className="sf-form__row"
        style={{ alignItems: "end", marginTop: "0.75rem" }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <InputField
          label={t("common.name")}
          id="bc-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <div className="sf-field">
          <Button type="submit" disabled={create.isPending || !name}>
            {t("common.add")}
          </Button>
        </div>
      </form>

      {editing && (
        <Modal
          title={t("common.edit")}
          onClose={() => setEditing(null)}
          size="wide"
          footer={
            <div className="sf-form__actions">
              <Button type="submit" form="bce-edit-form" disabled={save.isPending}>
                {t("common.save")}
              </Button>
            </div>
          }
        >
          <form
            id="bce-edit-form"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
              {editing.logo ? (
                <img className="sf-avatar" src={editing.logo.url} alt="" />
              ) : (
                <span className="sf-avatar sf-avatar--initials">—</span>
              )}
              <ImageUploader
                crop
                create={() => boatsService.uploadClassLogo(editing.id)}
                confirm={(imageId) => boatsService.confirmClassLogo(editing.id, imageId)}
                onDone={invalidate}
              />
            </div>
            <InputField
              label={t("common.name")}
              id="bce-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <RichTextField
              label={t("common.description")}
              id="bce-desc"
              value={form.description}
              onChange={(html) => setForm((f) => ({ ...f, description: html }))}
              tier="basic"
            />
            <div className="sf-form__row">
              <InputField
                label={t("admin.loa")}
                id="bce-loa"
                type="number"
                step="any"
                value={form.loa_m}
                onChange={(e) => setForm((f) => ({ ...f, loa_m: e.target.value }))}
              />
              <InputField
                label={t("admin.beam")}
                id="bce-beam"
                type="number"
                step="any"
                value={form.beam_m}
                onChange={(e) => setForm((f) => ({ ...f, beam_m: e.target.value }))}
              />
              <InputField
                label={t("admin.sailArea")}
                id="bce-sail"
                type="number"
                step="any"
                value={form.sail_area_sqm}
                onChange={(e) => setForm((f) => ({ ...f, sail_area_sqm: e.target.value }))}
              />
            </div>
            <div className="sf-form__row">
              <InputField
                label={t("admin.crewSize")}
                id="bce-crew"
                type="number"
                step="1"
                value={form.crew_size}
                onChange={(e) => setForm((f) => ({ ...f, crew_size: e.target.value }))}
              />
              <Select
                label={t("admin.hullType")}
                id="bce-hull"
                value={form.hull_type}
                onChange={(e) => setForm((f) => ({ ...f, hull_type: e.target.value }))}
              >
                <option value="">—</option>
                <option value="monohull">{t("admin.monohull")}</option>
                <option value="multihull">{t("admin.multihull")}</option>
              </Select>
              <Select
                label={t("admin.rigType")}
                id="bce-rig"
                value={form.rig_type}
                onChange={(e) => setForm((f) => ({ ...f, rig_type: e.target.value }))}
              >
                <option value="">—</option>
                <option value="sloop">{t("admin.sloop")}</option>
                <option value="una">{t("admin.una")}</option>
              </Select>
            </div>
            <div className="sf-form__row">
              <Select
                label={t("admin.spinnakerType")}
                id="bce-spinnaker"
                value={form.spinnaker_type}
                onChange={(e) => setForm((f) => ({ ...f, spinnaker_type: e.target.value }))}
              >
                <option value="">—</option>
                <option value="none">{t("admin.spinnaker_none")}</option>
                <option value="asymmetric">{t("admin.spinnaker_asymmetric")}</option>
                <option value="symmetric">{t("admin.spinnaker_symmetric")}</option>
              </Select>
              <InputField
                label={t("admin.pyRating")}
                id="bce-py"
                type="number"
                step="1"
                value={form.py_rating}
                onChange={(e) => setForm((f) => ({ ...f, py_rating: e.target.value }))}
              />
              <InputField
                label={t("admin.ryaClassId")}
                id="bce-rya"
                type="number"
                step="1"
                value={form.rya_class_id}
                onChange={(e) => setForm((f) => ({ ...f, rya_class_id: e.target.value }))}
              />
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
