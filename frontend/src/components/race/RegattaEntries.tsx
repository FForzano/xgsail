import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, RefreshCw, Trash2 } from "lucide-react";
import { regattasService, raceKeys } from "@/services/races";
import { useToast } from "@/hooks/useToast";
import { BoatPicker, boatLabel } from "@/components/common/BoatPicker";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import type { UUID } from "@/types";

/** The regatta's start list, plus the share code that lets sailors add
 * themselves.
 *
 * Being on this list is what allows a competitor to tag a recording with one
 * of the regatta's races (see backend `can_attach_session_to_activity`), so it
 * has to cover visiting boats too — hence the code, since the organizer can't
 * pre-enter every boat that will turn up. It is not the official race entry. */
export function RegattaEntries({ regattaId, manage }: { regattaId: UUID; manage: boolean }) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [boatId, setBoatId] = useState<UUID | "">("");

  const entries = useQuery({
    queryKey: raceKeys.entries(regattaId),
    queryFn: () => regattasService.entries(regattaId),
  });
  const joinCode = useQuery({
    queryKey: raceKeys.joinCode(regattaId),
    queryFn: () => regattasService.joinCode(regattaId),
    enabled: manage,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: raceKeys.entries(regattaId) });
  const invalidateCode = () =>
    queryClient.invalidateQueries({ queryKey: raceKeys.joinCode(regattaId) });

  const add = useMutation({
    mutationFn: () => regattasService.addEntry(regattaId, boatId as UUID),
    onSuccess: async () => {
      setBoatId("");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: UUID) => regattasService.removeEntry(regattaId, id),
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const regenerate = useMutation({
    mutationFn: () => regattasService.regenerateJoinCode(regattaId),
    onSuccess: invalidateCode,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const revoke = useMutation({
    mutationFn: () => regattasService.revokeJoinCode(regattaId),
    onSuccess: invalidateCode,
    onError: () => notify(t("errors.generic"), "error"),
  });

  const rows = entries.data ?? [];
  const code = joinCode.data?.join_code ?? null;
  const joinUrl = code ? `${window.location.origin}/regate/${regattaId}/join?code=${code}` : null;

  const copyLink = async () => {
    if (!joinUrl) return;
    await navigator.clipboard.writeText(joinUrl);
    notify(t("common.copied"), "success");
  };

  return (
    <div>
      {rows.length === 0 ? (
        <EmptyState>{t("regate.noEntries")}</EmptyState>
      ) : (
        <div className="sf-tablewrap">
          <table className="sf-table">
            <thead>
              <tr>
                <th>{t("race.boat")}</th>
                <th>{t("regate.entrySource")}</th>
                {manage && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td>{e.boat ? boatLabel(e.boat) : e.boat_id.slice(0, 8)}</td>
                  <td>
                    <span className="sf-badge">{t(`regate.entrySource_${e.source}`)}</span>
                  </td>
                  {manage && (
                    <td>
                      <Button
                        variant="ghost"
                        className="sf-btn--icon-sm"
                        aria-label={t("common.remove")}
                        onClick={() => remove.mutate(e.boat_id)}
                      >
                        <Trash2 size={16} />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {manage && (
        <>
          <form
            className="sf-form__row"
            style={{ alignItems: "end", marginTop: "0.75rem" }}
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              if (boatId) add.mutate();
            }}
          >
            <BoatPicker
              id="entry-boat"
              label={t("regate.addEntry")}
              value={boatId}
              onChange={setBoatId}
              exclude={rows.map((e) => e.boat_id)}
            />
            <Button type="submit" disabled={!boatId || add.isPending}>
              {t("common.add")}
            </Button>
          </form>

          <div className="sf-field" style={{ marginTop: "1rem" }}>
            <span className="sf-field__label">{t("regate.joinCode")}</span>
            <p className="sf-muted">{t("regate.joinCodeHint")}</p>
            {code ? (
              <div className="sf-strip__item sf-strip__item--muted">
                <code>{code}</code>
                <span style={{ display: "flex", gap: "0.25rem" }}>
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("regate.copyJoinLink")}
                    onClick={copyLink}
                  >
                    <Copy size={16} />
                  </Button>
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("regate.regenerateJoinCode")}
                    onClick={() => regenerate.mutate()}
                  >
                    <RefreshCw size={16} />
                  </Button>
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("regate.revokeJoinCode")}
                    onClick={() => revoke.mutate()}
                  >
                    <Trash2 size={16} />
                  </Button>
                </span>
              </div>
            ) : (
              <Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>
                {t("regate.createJoinCode")}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
