import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usersService, userKeys } from "@/services/users";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { Avatar } from "@/components/ui/Avatar";
import { unitsStore, useUnits } from "@/stores/unitsStore";

export function AnagraficaPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const me = useQuery({ queryKey: userKeys.me, queryFn: usersService.me });
  const units = useUnits();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    dob: "",
    // Optional, and used for one thing only: the heart-rate zones on a
    // session's health card (see components/session/HealthCard). Kept as
    // strings so an empty field stays empty rather than becoming 0.
    resting_hr_bpm: "",
    max_hr_bpm: "",
  });

  const saveUnits = useMutation({
    mutationFn: (unit_system: "nautical" | "metric") =>
      usersService.update(user!.id, { unit_system }),
    onSuccess: async (_, unit_system) => {
      unitsStore.set(unit_system);
      await queryClient.invalidateQueries({ queryKey: userKeys.me });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  useEffect(() => {
    if (me.data) {
      setForm({
        first_name: me.data.first_name ?? "",
        last_name: me.data.last_name ?? "",
        dob: me.data.dob ?? "",
        resting_hr_bpm: me.data.resting_hr_bpm?.toString() ?? "",
        max_hr_bpm: me.data.max_hr_bpm?.toString() ?? "",
      });
    }
  }, [me.data]);

  const save = useMutation({
    mutationFn: () =>
      usersService.update(user!.id, {
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        dob: form.dob || null,
        resting_hr_bpm: form.resting_hr_bpm ? Number(form.resting_hr_bpm) : null,
        max_hr_bpm: form.max_hr_bpm ? Number(form.max_hr_bpm) : null,
      }),
    onSuccess: async () => {
      notify(t("common.saved"), "success");
      await queryClient.invalidateQueries({ queryKey: userKeys.me });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (me.isLoading) return <Spinner />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <div className="sf-grid" style={{ gridTemplateColumns: "minmax(280px, 480px)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
        <Avatar
          size="lg"
          profileImage={me.data?.profile_image ?? null}
          firstName={me.data?.first_name}
          lastName={me.data?.last_name}
        />
        <ImageUploader
          label={t("profile.profileImage")}
          create={usersService.createProfileImage}
          confirm={(id) => usersService.confirmProfileImage(id)}
          crop
          onDone={async () => {
            await queryClient.invalidateQueries({ queryKey: userKeys.me });
          }}
        />
      </div>
      <form onSubmit={onSubmit} data-tour="profilo-anagrafica">
        <InputField
          label={t("profile.firstName")}
          id="first_name"
          value={form.first_name}
          onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
        />
        <InputField
          label={t("profile.lastName")}
          id="last_name"
          value={form.last_name}
          onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
        />
        <InputField label={t("auth.email")} id="email" value={me.data?.email ?? ""} disabled />
        <InputField
          label={t("profile.dob")}
          id="dob"
          type="date"
          value={form.dob}
          onChange={(e) => setForm((f) => ({ ...f, dob: e.target.value }))}
        />
        {/* Health data, and health data only: these two exist so a session's
            heart-rate zones can be worked out. Nothing else reads them, and
            nobody else sees them — only the resulting zone boundaries are
            shared, and only with whoever you share the session's health data
            with. */}
        <p className="sf-muted" style={{ fontSize: "0.8rem", margin: "0.75rem 0 0.25rem" }}>
          {t("profile.hrHint")}
        </p>
        <InputField
          label={t("profile.restingHr")}
          id="resting_hr_bpm"
          type="number"
          min={30}
          max={120}
          value={form.resting_hr_bpm}
          onChange={(e) => setForm((f) => ({ ...f, resting_hr_bpm: e.target.value }))}
        />
        <InputField
          label={t("profile.maxHr")}
          id="max_hr_bpm"
          type="number"
          min={100}
          max={240}
          value={form.max_hr_bpm}
          onChange={(e) => setForm((f) => ({ ...f, max_hr_bpm: e.target.value }))}
        />
        <div className="sf-form__actions">
          <Button type="submit" disabled={save.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
      {/* Card has no pass-through prop for arbitrary DOM attributes, so the
          anchor goes on a thin wrapper instead of touching the shared component. */}
      <div data-tour="profilo-units">
        <Card title={t("profile.units")}>
          <div className="sf-form__row">
            <button
              type="button"
              className={`sf-btn sf-btn--sm ${units === "nautical" ? "sf-btn--primary" : "sf-btn--ghost"}`}
              disabled={saveUnits.isPending}
              onClick={() => saveUnits.mutate("nautical")}
            >
              {t("profile.unitsNautical")}
            </button>
            <button
              type="button"
              className={`sf-btn sf-btn--sm ${units === "metric" ? "sf-btn--primary" : "sf-btn--ghost"}`}
              disabled={saveUnits.isPending}
              onClick={() => saveUnits.mutate("metric")}
            >
              {t("profile.unitsMetric")}
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}
