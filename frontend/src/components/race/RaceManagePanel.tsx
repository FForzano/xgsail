import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { racesService, raceKeys } from "@/services/races";
import { activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { ResultsEditor } from "./ResultsEditor";
import type { MapMark } from "./MapView";
import type { Race, UUID } from "@/types";

/** Management actions on the race dashboard, gated per scoped permission:
 * race.manage → start time / match-sessions / boat GPX; mark.manage →
 * auto-start-line + suggest-marks with preview-then-apply; result.manage →
 * results editor. */
export function RaceManagePanel({
  race,
  canRace,
  canMarks,
  canResults,
  onPreviewMarks,
}: {
  race: Race;
  canRace: boolean;
  canMarks: boolean;
  canResults: boolean;
  onPreviewMarks: (marks: MapMark[]) => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [gpxBoat, setGpxBoat] = useState("");
  const [startTime, setStartTime] = useState(
    race.start_time ? race.start_time.slice(0, 16) : "",
  );
  const [preview, setPreview] = useState<"start" | "marks" | null>(null);

  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });

  const onError = (err: unknown) =>
    notify(err instanceof ApiError ? err.detail : t("errors.generic"), "error");

  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: raceKeys.race(race.id) });
    await queryClient.invalidateQueries({ queryKey: raceKeys.data(race.id) });
    if (race.activity_id) {
      await queryClient.invalidateQueries({ queryKey: activityKeys.marks(race.activity_id) });
    }
  };

  const saveStart = useMutation({
    mutationFn: () =>
      racesService.update(race.id, {
        start_time: new Date(startTime).toISOString(),
      }),
    onSuccess: async () => {
      notify(t("common.saved"), "success");
      await invalidateAll();
    },
    onError,
  });

  const match = useMutation({
    mutationFn: () => racesService.matchSessions(race.id),
    onSuccess: async (res) => {
      notify(`${t("race.matched")}: ${(res.matched as unknown[]).length}`, "success");
      await invalidateAll();
    },
    onError,
  });

  const startLine = useMutation({
    mutationFn: (apply: boolean) => racesService.autoStartLine(race.id, apply),
    onSuccess: async (res, apply) => {
      if (!apply) {
        const marks: MapMark[] = [];
        for (const role of ["pin", "rc"] as const) {
          const p = res[role] as { lat: number; lon?: number; lng?: number } | undefined;
          if (p) marks.push({ mark_role: role, lat: p.lat, lng: p.lng ?? p.lon ?? 0, preview: true });
        }
        onPreviewMarks(marks);
        setPreview("start");
      } else {
        onPreviewMarks([]);
        setPreview(null);
        await invalidateAll();
      }
    },
    onError,
  });

  const suggest = useMutation({
    mutationFn: (apply: boolean) => racesService.suggestMarks(race.id, apply),
    onSuccess: async (res, apply) => {
      if (!apply) {
        const marks: MapMark[] = (res.marks ?? []).map((m) => {
          const raw = m as { mark_role?: string; lat?: number; lon?: number; lng?: number };
          return {
            mark_role: raw.mark_role ?? "mark",
            lat: raw.lat ?? 0,
            lng: raw.lng ?? raw.lon ?? 0,
            preview: true,
          };
        });
        onPreviewMarks(marks);
        setPreview("marks");
      } else {
        onPreviewMarks([]);
        setPreview(null);
        await invalidateAll();
      }
    },
    onError,
  });

  const uploadGpx = useMutation({
    mutationFn: ({ boatId, file }: { boatId: UUID; file: File }) =>
      racesService.uploadBoatGpx(race.id, boatId, file),
    onSuccess: async () => {
      notify(t("common.saved"), "success");
      await invalidateAll();
    },
    onError,
  });

  return (
    <Card title={t("race.manage")}>
      {canRace && (
        <>
          <form
            className="sf-form__row"
            style={{ alignItems: "end" }}
            onSubmit={(e) => {
              e.preventDefault();
              if (startTime) saveStart.mutate();
            }}
          >
            <InputField
              label={t("regate.startTime")}
              id="race-start"
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
            />
            <div className="sf-field">
              <Button type="submit" disabled={saveStart.isPending || !startTime}>
                {t("common.save")}
              </Button>
            </div>
          </form>
          {!race.start_time && <p className="sf-muted">{t("race.setStartTime")}</p>}
          <div className="sf-form__actions" style={{ justifyContent: "flex-start" }}>
            <Button
              variant="ghost"
              disabled={match.isPending || !race.start_time}
              onClick={() => match.mutate()}
            >
              {t("race.matchSessions")}
            </Button>
          </div>
          <form
            className="sf-form__row"
            style={{ alignItems: "end" }}
            onSubmit={(e) => {
              e.preventDefault();
              const file = fileRef.current?.files?.[0];
              if (file && gpxBoat) uploadGpx.mutate({ boatId: gpxBoat as UUID, file });
            }}
          >
            <Select
              label={t("race.uploadGpx")}
              id="gpx-boat"
              value={gpxBoat}
              onChange={(e) => setGpxBoat(e.target.value)}
            >
              <option value="">…</option>
              {boats.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
            <label className="sf-field">
              <span className="sf-field__label">GPX</span>
              <input ref={fileRef} type="file" accept=".gpx" className="sf-field__input" />
            </label>
            <div className="sf-field">
              <Button type="submit" variant="ghost" disabled={uploadGpx.isPending || !gpxBoat}>
                {t("common.upload")}
              </Button>
            </div>
          </form>
        </>
      )}

      {canMarks && (
        <div className="sf-form__actions" style={{ justifyContent: "flex-start", flexWrap: "wrap" }}>
          <Button variant="ghost" disabled={startLine.isPending} onClick={() => startLine.mutate(false)}>
            {t("race.autoStartLine")} ({t("common.preview")})
          </Button>
          <Button variant="ghost" disabled={suggest.isPending} onClick={() => suggest.mutate(false)}>
            {t("race.suggestMarks")} ({t("common.preview")})
          </Button>
          {preview === "start" && (
            <Button disabled={startLine.isPending} onClick={() => startLine.mutate(true)}>
              {t("race.autoStartLine")} — {t("common.apply")}
            </Button>
          )}
          {preview === "marks" && (
            <Button disabled={suggest.isPending} onClick={() => suggest.mutate(true)}>
              {t("race.applyMarks")}
            </Button>
          )}
        </div>
      )}

      {canResults && (
        <>
          <h3>{t("race.results")}</h3>
          <ResultsEditor raceId={race.id} results={race.results ?? []} />
        </>
      )}
    </Card>
  );
}
