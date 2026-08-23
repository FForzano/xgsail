import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil } from "lucide-react";
import { regattasService, raceKeys, type OfficialStandingInput } from "@/services/races";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useRegattaMeta } from "@/hooks/useRegattaMeta";
import { useToast } from "@/hooks/useToast";
import { Section } from "@/components/ui/Section";
import { Button } from "@/components/ui/Button";
import { Menu, type MenuSection } from "@/components/ui/Menu";
import { Modal } from "@/components/ui/Modal";
import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { InputField } from "@/components/ui/InputField";
import { RichTextField } from "@/components/ui/RichTextField";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { BackLink } from "@/components/ui/BackLink";
import { StatTile, StatTiles } from "@/components/session/StatTile";
import { RegattaRaceDays } from "@/components/gruppi/RegattaRaceDays";
import { RegattaDivisions } from "@/components/race/RegattaDivisions";
import { RegattaEntries } from "@/components/race/RegattaEntries";
import { RegattaHero } from "@/components/race/RegattaHero";
import { RegattaStandings } from "@/components/race/RegattaStandings";
import { MyRegattaCard } from "@/components/race/MyRegattaCard";
import type { UUID } from "@/types";
import styles from "./RegattaDetailPage.module.css";

/** Which organizer task the ⋮ menu currently has open. */
type ManagePanel = "edit" | "days" | "divisions" | "entries" | "official";

/** Regatta detail page: hero, totals, the viewer's own standing, the
 * standings, the schedule and the start list — one flat stack of `Section`s,
 * read top to bottom by a competitor.
 *
 * Everything an organizer can change lives behind the single ⋮ menu on the
 * hero (gated on `regatta.manage`), each item opening one modal, instead of
 * management controls interleaved with the content a competitor came for. The
 * one deliberate exception is the pencil on the schedule section, which opens
 * the same race-days modal from where the schedule is shown. */
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
  // Same query key as `RegattaStandings`'s own fetch, so this shares its cache
  // entry rather than doubling the request — needed here only to know
  // `is_official` and prefill the override editor with the current ranking.
  const standings = useQuery({
    queryKey: raceKeys.standings(regattaId!),
    queryFn: () => regattasService.standings(regattaId!),
    enabled: !!regattaId,
  });
  const { clubName, boatClassName, raceCount } = useRegattaMeta(regatta.data);

  const [panel, setPanel] = useState<ManagePanel | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });
  const [officialRows, setOfficialRows] = useState<
    Record<UUID, { position: string; score: string; division_id?: UUID | null }>
  >({});

  useEffect(() => {
    if (regatta.data) {
      setForm({
        name: regatta.data.name ?? "",
        description: regatta.data.description ?? "",
      });
    }
  }, [regatta.data]);

  // Which of the viewer's own boats is on this start list — drives both the
  // personal card and the highlighted row in the standings.
  const myBoatId = useMemo(() => {
    const mine = new Set((myBoats.data ?? []).map((b) => b.id));
    return entries.data?.find((e) => e.boat_id && mine.has(e.boat_id))?.boat_id ?? null;
  }, [entries.data, myBoats.data]);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: raceKeys.regatta(regattaId!) });

  const save = useMutation({
    mutationFn: () =>
      regattasService.update(regattaId!, {
        name: form.name,
        description: form.description || null,
      }),
    onSuccess: async () => {
      setPanel(null);
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const invalidateStandings = () =>
    queryClient.invalidateQueries({ queryKey: raceKeys.standings(regattaId!) });

  const openOfficialEditor = () => {
    const initial: Record<UUID, { position: string; score: string; division_id?: UUID | null }> =
      {};
    (standings.data?.standings ?? []).forEach((row) => {
      initial[row.boat.id] = {
        position: String(row.rank),
        score: row.total ? String(row.total) : "",
        division_id: row.division_id,
      };
    });
    setOfficialRows(initial);
    setPanel("official");
  };

  const setOfficial = useMutation({
    mutationFn: () => {
      const payload: OfficialStandingInput[] = Object.entries(officialRows)
        .filter(([, v]) => v.position.trim() !== "")
        .map(([boatId, v]) => ({
          boat_id: boatId as UUID,
          position: Number(v.position),
          ...(v.score.trim() ? { score: Number(v.score) } : {}),
          ...(v.division_id !== undefined ? { division_id: v.division_id } : {}),
        }));
      return regattasService.setOfficialStandings(regattaId!, payload);
    },
    onSuccess: async () => {
      setPanel(null);
      notify(t("common.saved"), "success");
      await invalidateStandings();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  const clearOfficial = useMutation({
    mutationFn: () => regattasService.clearOfficialStandings(regattaId!),
    onSuccess: async () => {
      notify(t("regate.officialStandingsCleared"), "success");
      await invalidateStandings();
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

  const menuSections: MenuSection[] = [
    {
      items: [{ label: t("regate.editRegatta"), onClick: () => setPanel("edit") }],
    },
    {
      heading: t("regate.organization"),
      items: [
        { label: t("regate.manageRaceDays"), onClick: () => setPanel("days") },
        {
          label: t("regate.manageDivisions"),
          onClick: () => setPanel("divisions"),
        },
        {
          label: t("regate.manageEntries"),
          onClick: () => setPanel("entries"),
        },
      ],
    },
    {
      heading: t("regate.standings"),
      items: [
        {
          label: t("regate.manageOfficialStandings"),
          onClick: openOfficialEditor,
        },
        // Only meaningful while a published ranking is actually overriding the
        // computed one.
        ...(standings.data?.is_official
          ? [
              {
                label: t("regate.clearOfficialStandings"),
                danger: true,
                disabled: clearOfficial.isPending,
                onClick: () => clearOfficial.mutate(),
              },
            ]
          : []),
      ],
    },
  ];

  return (
    <div className="sf-section__body">
      <BackLink fallback={`/gruppi/clubs/${r.club_id}/eventi`} label={t("regate.backToEvents")} />

      <RegattaHero
        regatta={r}
        clubName={clubName}
        boatClassName={boatClassName}
        raceCount={raceCount}
        onOpenImage={r.image ? () => setLightboxOpen(true) : undefined}
        actions={manage ? <Menu sections={menuSections} /> : undefined}
      />

      <StatTiles>
        <StatTile label={t("regate.statDays")} value={days.length} />
        <StatTile label={t("regate.statRaces")} value={raceCount} />
        <StatTile label={t("regate.statEntries")} value={entries.data?.length ?? "—"} />
        <StatTile label={t("regate.statFinished")} value={finishedRaces} />
      </StatTiles>

      <MyRegattaCard regattaId={regattaId} boatId={myBoatId} />

      <Section title={t("regate.standings")}>
        <RegattaStandings
          regattaId={regattaId}
          highlightBoatId={myBoatId}
          dataTour="regatta-standings"
        />
      </Section>

      <Section
        // A one-day regatta has no days to speak of, only races.
        title={t(days.length === 1 ? "regate.races" : "regate.raceDays")}
        actions={
          manage ? (
            <Button
              variant="ghost"
              className="sf-btn--icon-sm"
              aria-label={t("regate.manageRaceDays")}
              title={t("regate.manageRaceDays")}
              onClick={() => setPanel("days")}
            >
              <Pencil size={16} />
            </Button>
          ) : undefined
        }
      >
        {/* RegattaRaceDays is shared with the diario feed's EventRow, so the
            anchor is wrapped at this call site instead of inside it. */}
        <div data-tour="regatta-racedays">
          <RegattaRaceDays regattaId={regattaId} manage={false} />
        </div>
      </Section>

      <Section title={t("regate.entries")}>
        <RegattaEntries regattaId={regattaId} manage={false} dataTour="regatta-entries" />
      </Section>

      {lightboxOpen && r.image && (
        <ImageLightbox src={r.image.url} alt="" onClose={() => setLightboxOpen(false)} />
      )}

      {panel === "edit" && (
        <Modal
          title={t("regate.editRegatta")}
          onClose={() => setPanel(null)}
          size="wide"
          footer={
            <div className="sf-form__actions">
              <Button type="submit" form="rg-edit-form" disabled={save.isPending || !form.name}>
                {t("common.save")}
              </Button>
            </div>
          }
        >
          <div className={`sf-field ${styles.posterField}`}>
            <span className="sf-field__label">{t("regate.posterImage")}</span>
            {r.image && <img className={styles.posterPreview} src={r.image.url} alt="" />}
            <ImageUploader
              create={() => regattasService.uploadImage(regattaId)}
              confirm={(id) => regattasService.confirmImage(regattaId, id)}
              onDone={invalidate}
              icon={<ImagePlus size={16} />}
              label={t("regate.uploadPoster")}
            />
          </div>
          <form
            id="rg-edit-form"
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
            <RichTextField
              label={t("common.description")}
              id="rg-desc"
              value={form.description}
              onChange={(html) => setForm((f) => ({ ...f, description: html }))}
              tier="basic"
            />
          </form>
        </Modal>
      )}

      {panel === "days" && (
        <Modal title={t("regate.manageRaceDays")} onClose={() => setPanel(null)}>
          <RegattaRaceDays regattaId={regattaId} manage />
        </Modal>
      )}

      {panel === "divisions" && (
        <Modal title={t("regate.manageDivisions")} onClose={() => setPanel(null)}>
          <RegattaDivisions regattaId={regattaId} canManage={manage} />
        </Modal>
      )}

      {panel === "entries" && (
        <Modal title={t("regate.manageEntries")} onClose={() => setPanel(null)}>
          <RegattaEntries regattaId={regattaId} manage />
        </Modal>
      )}

      {panel === "official" && (
        <Modal title={t("regate.manageOfficialStandings")} onClose={() => setPanel(null)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              setOfficial.mutate();
            }}
          >
            <p className="sf-muted">{t("regate.officialStandingsIntro")}</p>
            {/* Group rows by division so a published ranking stays grouped — with
                no divisions, this is a single unlabeled group, same as before. */}
            {(standings.data?.divisions.length
              ? standings.data.divisions.map((d) => ({
                  label: d.division?.name ?? t("regate.noDivision"),
                  rows: d.standings,
                }))
              : [{ label: null, rows: standings.data?.standings ?? [] }]
            ).map((group, i) => (
              <div key={group.label ?? i}>
                {group.label && <h4>{group.label}</h4>}
                {group.rows.map((row) => (
                  <div key={row.boat.id} className="sf-form__row">
                    <span>
                      {row.boat.name}
                      {row.boat.sail_number ? ` — ${row.boat.sail_number}` : ""}
                    </span>
                    <InputField
                      id={`official-pos-${row.boat.id}`}
                      label={t("race.position")}
                      type="number"
                      min={1}
                      value={officialRows[row.boat.id]?.position ?? ""}
                      onChange={(e) =>
                        setOfficialRows((r) => ({
                          ...r,
                          [row.boat.id]: {
                            score: r[row.boat.id]?.score ?? "",
                            division_id: r[row.boat.id]?.division_id ?? row.division_id,
                            position: e.target.value,
                          },
                        }))
                      }
                    />
                    <div>
                      <InputField
                        id={`official-score-${row.boat.id}`}
                        label={t("regate.officialTotalScore")}
                        type="number"
                        value={officialRows[row.boat.id]?.score ?? ""}
                        onChange={(e) =>
                          setOfficialRows((r) => ({
                            ...r,
                            [row.boat.id]: {
                              position: r[row.boat.id]?.position ?? "",
                              division_id: r[row.boat.id]?.division_id ?? row.division_id,
                              score: e.target.value,
                            },
                          }))
                        }
                      />
                      <p className="sf-muted">{t("regate.officialTotalScoreHint")}</p>
                    </div>
                  </div>
                ))}
              </div>
            ))}
            <div className="sf-form__actions">
              <Button type="submit" disabled={setOfficial.isPending}>
                {t("regate.publishOfficialStandings")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
