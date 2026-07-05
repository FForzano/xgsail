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

export function AnagraficaPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const me = useQuery({ queryKey: userKeys.me, queryFn: usersService.me });
  const [form, setForm] = useState({ first_name: "", last_name: "", dob: "" });

  useEffect(() => {
    if (me.data) {
      setForm({
        first_name: me.data.first_name ?? "",
        last_name: me.data.last_name ?? "",
        dob: me.data.dob ?? "",
      });
    }
  }, [me.data]);

  const save = useMutation({
    mutationFn: () =>
      usersService.update(user!.id, {
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        dob: form.dob || null,
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
      <Card title={t("profile.details")}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
          {me.data?.profile_image ? (
            <img className="sf-avatar sf-avatar--lg" src={me.data.profile_image.url} alt="" />
          ) : (
            <div className="sf-avatar sf-avatar--lg" />
          )}
          <ImageUploader
            label={t("profile.profileImage")}
            create={usersService.createProfileImage}
            confirm={(id) => usersService.confirmProfileImage(id)}
            onDone={async () => {
              await queryClient.invalidateQueries({ queryKey: userKeys.me });
            }}
          />
        </div>
        <form onSubmit={onSubmit}>
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
          <div className="sf-form__actions">
            <Button type="submit" disabled={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
