import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil } from "lucide-react";
import { regattasService, raceKeys } from "@/services/races";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { BackLink } from "@/components/ui/BackLink";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import type { UUID } from "@/types";

/** Regatta detail page (name, hero image, description, race days/races) —
 * reachable from a race's dashboard (`RacePage`'s back link) or from the
 * club's Eventi tab. Race-day/race management is the same
 * `RegattaRaceDays` block used inline there, just full-page here. */
export function RegattaDetailPage() {
  const { regattaId } = useParams<{ regattaId: UUID }>();
  const { t } = useTranslation();
  const { can } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const regatta = useQuery({
    queryKey: raceKeys.regatta(regattaId!),
    queryFn: () => regattasService.get(regattaId!),
    enabled: !!regattaId,
  });

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });

  useEffect(() => {
    if (regatta.data) {
      setForm({ name: regatta.data.name ?? "", description: regatta.data.description ?? "" });
    }
  }, [regatta.data]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: raceKeys.regatta(regattaId!) });

  const save = useMutation({
    mutationFn: () =>
      regattasService.update(regattaId!, {
        name: form.name,
        description: form.description || null,
      }),
    onSuccess: async () => {
      setEditing(false);
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (regatta.isLoading || !regattaId) return <Spinner />;
  if (!regatta.data) return null;
  const r = regatta.data;
  const manage = can("regatta.manage", r.club_id);

  return (
    <div className="sf-section__body">
      <BackLink to={`/gruppi/clubs/${r.club_id}/eventi`} label={t("regate.backToEvents")} />
      <Card>
        <div className="sf-entity-header">
          <div className="sf-entity-header__identity">
            {r.image && <img className="sf-avatar sf-avatar--lg" src={r.image.url} alt="" />}
            <div>
              <h1 className="sf-entity-header__name">{r.name}</h1>
              {r.description && <p className="sf-muted sf-entity-header__meta">{r.description}</p>}
            </div>
          </div>
          {manage && (
            <div className="sf-entity-header__actions">
              <ImageUploader
                create={() => regattasService.uploadImage(regattaId)}
                confirm={(id) => regattasService.confirmImage(regattaId, id)}
                onDone={invalidate}
                crop
                icon={<ImagePlus size={16} />}
                label={t("common.upload")}
              />
              <Button
                variant="ghost"
                className="sf-btn--icon-sm"
                aria-label={t("regate.editRegatta")}
                onClick={() => setEditing(true)}
              >
                <Pencil size={16} />
              </Button>
            </div>
          )}
        </div>
      </Card>

      <Card title={t("regate.raceDays")}>
        <RegattaRaceDays regattaId={regattaId} manage={manage} />
      </Card>

      {editing && (
        <Modal title={t("regate.editRegatta")} onClose={() => setEditing(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="rg-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <TextAreaField
              label={t("common.description")}
              id="rg-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <div className="sf-form__actions">
              <Button type="submit" disabled={save.isPending || !form.name}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
