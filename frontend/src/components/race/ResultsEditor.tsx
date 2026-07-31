import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { racesService, raceKeys } from "@/services/races";
import { useBoatNames } from "@/hooks/useBoatNames";
import { useToast } from "@/hooks/useToast";
import { BoatPicker } from "@/components/common/BoatPicker";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import type { RaceResult, UUID } from "@/types";

const RESULT_STATUSES = ["finished", "dnf", "dns", "dsq", "ocs", "ret"];

/** Official results entry (result.manage): one row per boat, PUT upsert. */
export function ResultsEditor({ raceId, results }: { raceId: UUID; results: RaceResult[] }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const boatName = useBoatNames(results.map((r) => r.boat_id));

  const [boatId, setBoatId] = useState("");
  const [position, setPosition] = useState("");
  const [status, setStatus] = useState("finished");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: raceKeys.race(raceId) });

  const upsert = useMutation({
    mutationFn: () =>
      racesService.upsertResult(raceId, boatId as UUID, {
        position: position ? Number(position) : null,
        status,
      }),
    onSuccess: async () => {
      setBoatId("");
      setPosition("");
      setStatus("finished");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (bId: UUID) => racesService.removeResult(raceId, bId),
    onSuccess: invalidate,
  });

  return (
    <div>
      {results.length > 0 && (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("race.position")}</th>
                <th>{t("race.boat")}</th>
                <th>{t("race.resultStatus")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {[...results]
                .sort((a, b) => (a.position ?? 99) - (b.position ?? 99))
                .map((r) => (
                  <tr key={r.boat_id}>
                    <td>{r.position ?? "—"}</td>
                    <td>{boatName(r.boat_id)}</td>
                    <td>
                      <span className="sf-badge">{r.status}</span>
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        className="sf-btn--sm"
                        onClick={() => remove.mutate(r.boat_id)}
                      >
                        {t("common.remove")}
                      </Button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
      <form
        className="sf-form__row"
        style={{ alignItems: "end", marginTop: "0.75rem" }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (boatId) upsert.mutate();
        }}
      >
        <BoatPicker
          id="res-boat"
          label={t("race.boat")}
          value={boatId as UUID | ""}
          onChange={(id) => setBoatId(id)}
        />
        <InputField
          label={t("race.position")}
          id="res-pos"
          type="number"
          min={1}
          value={position}
          onChange={(e) => setPosition(e.target.value)}
        />
        <Select
          label={t("race.resultStatus")}
          id="res-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {RESULT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
        <div className="sf-field">
          <Button type="submit" disabled={upsert.isPending || !boatId}>
            {t("race.saveResult")}
          </Button>
        </div>
      </form>
    </div>
  );
}
