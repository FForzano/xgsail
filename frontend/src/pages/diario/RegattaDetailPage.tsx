import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil } from "lucide-react";
import { regattasService, raceKeys } from "@/services/races";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useRegattaMeta } from "@/hooks/useRegattaMeta";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { BackLink } from "@/components/ui/BackLink";
import { StatTile, StatTiles } from "@/components/session/StatTile";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import { RegattaEntries } from "@/components/race/RegattaEntries";
import { RegattaHero } from "@/components/race/RegattaHero";
import { RegattaStandings } from "@/components/race/RegattaStandings";
import { MyRegattaCard } from "@/components/race/MyRegattaCard";
import type { UUID } from "@/types";

/** Regatta detail page (name, poster, standings, race days/races, start list)
 * — reachable from a race's dashboard (`RacePage`'s back link) or from the
 * club's Eventi tab. Ordered for the competitor first (hero, totals, their own
 * standing, the standings table) and the organizer last (race-day and start
 * list management), rather than putting the admin blocks up top. */
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
  const entries = useQuery({
    queryKey: raceKeys.entries(regattaId!),
    queryFn: () => regattasService.entries(regattaId!),
    enabled: !!regattaId,
  });
  const myBoats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });
  const { clubName, boatClassName, raceCount } = useRegattaMeta(regatta.data);

  const [editing, setEditing] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });

  useEffect(() => {
    if (regatta.data) {
      setForm({ name: regatta.data.name ?? "", description: regatta.data.description ?? "" });
    }
  }, [regatta.data]);

  // Which of the viewer's own boats is on this start list — drives both the
  // personal card and the highlighted row in the standings.
  const myBoatId = useMemo(() => {
    const mine = new Set((myBoats.data ?? []).map((b) => b.id));
    return entries.data?.find((e) => mine.has(e.boat_id))?.boat_id ?? null;
  }, [entries.data, myBoats.data]);

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
  const days = r.race_days ?? [];
  const finishedRaces = days.reduce(
    (n, day) => n + (day.races ?? []).filter((race) => race.status === "finished").length,
    0,
  );

  return (
    <div className="sf-section__body">
      <BackLink fallback={`/gruppi/clubs/${r.club_id}/eventi`} label={t("regate.backToEvents")} />

      <RegattaHero
        regatta={r}
        clubName={clubName}
        boatClassName={boatClassName}
        raceCount={raceCount}
        onOpenImage={r.image ? () => setLightboxOpen(true) : undefined}
        actions={
          manage && (
            <>
              <ImageUploader
                create={() => regattasService.uploadImage(regattaId)}
                confirm={(id) => regattasService.confirmImage(regattaId, id)}
                onDone={invalidate}
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
            </>
          )
        }
      />

      <StatTiles>
        <StatTile label={t("regate.statDays")} value={days.length} />
        <StatTile label={t("regate.statRaces")} value={raceCount} />
        <StatTile label={t("regate.statEntries")} value={entries.data?.length ?? "—"} />
        <StatTile label={t("regate.statFinished")} value={finishedRaces} />
      </StatTiles>

      <MyRegattaCard regattaId={regattaId} boatId={myBoatId} />

      <Card title={t("regate.standings")}>
        <RegattaStandings regattaId={regattaId} highlightBoatId={myBoatId} />
      </Card>

      <Card title={t("regate.raceDays")}>
        <RegattaRaceDays regattaId={regattaId} manage={manage} />
      </Card>

      <Card title={t("regate.entries")}>
        <RegattaEntries regattaId={regattaId} manage={manage} />
      </Card>

      {lightboxOpen && r.image && (
        <ImageLightbox src={r.image.url} alt="" onClose={() => setLightboxOpen(false)} />
      )}

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
