import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, RefreshCw, Trash2, UserPlus, X } from "lucide-react";
import { regattasService, raceKeys } from "@/services/races";
import { publicWebOrigin } from "@/config/platform";
import { useToast } from "@/hooks/useToast";
import { BoatPicker } from "@/components/common/BoatPicker";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { EmptyState } from "@/components/ui/EmptyState";
import type { UUID } from "@/types";
import styles from "./RegattaEntries.module.css";

/** The regatta's start list, plus the share link that lets sailors add
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
  const [manualName, setManualName] = useState("");
  const [manualSail, setManualSail] = useState("");
  const [linkingEntryId, setLinkingEntryId] = useState<UUID | null>(null);
  const [linkBoatId, setLinkBoatId] = useState<UUID | "">("");
  const [manualFormOpen, setManualFormOpen] = useState(false);

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
  const addManual = useMutation({
    mutationFn: () => regattasService.addManualEntry(regattaId, manualName.trim(), manualSail.trim() || null),
    onSuccess: async () => {
      setManualName("");
      setManualSail("");
      setManualFormOpen(false);
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const remove = useMutation({
    mutationFn: (entryId: UUID) => regattasService.removeEntry(regattaId, entryId),
    onSuccess: invalidate,
    onError: () => notify(t("errors.generic"), "error"),
  });
  const link = useMutation({
    mutationFn: ({ entryId, boatId }: { entryId: UUID; boatId: UUID }) =>
      regattasService.linkEntry(regattaId, entryId, boatId),
    onSuccess: async () => {
      setLinkingEntryId(null);
      setLinkBoatId("");
      await invalidate();
    },
    onError: () => notify(t("regate.linkEntryFailed"), "error"),
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
  const joinUrl = code ? `${publicWebOrigin}/regate/${regattaId}/join?code=${code}` : null;

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
        <div className={styles.boatGrid}>
          {rows.map((e) => (
            <div key={e.id} className={styles.boatChip}>
              <span className={styles.boatIdentity}>
                <span className={styles.boatName}>{e.display_name}</span>
                {e.display_sail_number && (
                  <span className={styles.sailNumber}>{e.display_sail_number}</span>
                )}
              </span>
              {!e.boat_id && (
                <span className="sf-badge sf-badge--sm">{t("regate.manualEntry")}</span>
              )}
              <span className="sf-badge sf-badge--sm">{t(`regate.entrySource_${e.source}`)}</span>
              {manage && !e.boat_id && (
                <button
                  className={styles.removeBoat}
                  aria-label={t("regate.linkEntry")}
                  title={t("regate.linkEntry")}
                  onClick={() => setLinkingEntryId(linkingEntryId === e.id ? null : e.id)}
                >
                  <Link2 size={14} />
                </button>
              )}
              {manage && (
                <button
                  className={styles.removeBoat}
                  aria-label={t("common.remove")}
                  onClick={() => remove.mutate(e.id)}
                >
                  <X size={14} />
                </button>
              )}
              {manage && linkingEntryId === e.id && (
                <form
                  className={`sf-form__row ${styles.linkForm}`}
                  onSubmit={(ev: FormEvent) => {
                    ev.preventDefault();
                    if (linkBoatId) link.mutate({ entryId: e.id, boatId: linkBoatId });
                  }}
                >
                  <BoatPicker
                    id={`link-boat-${e.id}`}
                    label={t("regate.linkEntry")}
                    value={linkBoatId}
                    onChange={setLinkBoatId}
                    exclude={rows.map((r) => r.boat_id).filter((id): id is UUID => !!id)}
                  />
                  <Button type="submit" disabled={!linkBoatId || link.isPending}>
                    {t("common.save")}
                  </Button>
                </form>
              )}
            </div>
          ))}
        </div>
      )}

      {manage && (
        <>
          <form
            className={`sf-form__row ${styles.addForm}`}
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
              exclude={rows.map((e) => e.boat_id).filter((id): id is UUID => !!id)}
            />
            <Button type="submit" disabled={!boatId || add.isPending}>
              {t("common.add")}
            </Button>
          </form>

          {/* For a boat with no record on the instance yet — a visitor entered
              by name until they register (or get linked to) a real boat. Kept
              behind a disclosure so the common case (BoatPicker above) isn't
              visually confused with this fallback for occasional visitors. */}
          <div className={styles.manualSection}>
            {!manualFormOpen ? (
              <Button
                variant="ghost"
                onClick={() => setManualFormOpen(true)}
              >
                <UserPlus size={16} /> {t("regate.manualEntryToggle")}
              </Button>
            ) : (
              <div className={styles.manualPanel}>
                <p className={`sf-muted ${styles.manualHint}`}>{t("regate.manualEntryHint")}</p>
                <form
                  className={`sf-form__row ${styles.addForm}`}
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    if (manualName.trim()) addManual.mutate();
                  }}
                >
                  <InputField
                    id="entry-manual-name"
                    label={t("regate.manualEntryName")}
                    value={manualName}
                    onChange={(e) => setManualName(e.target.value)}
                    required
                  />
                  <InputField
                    id="entry-manual-sail"
                    label={t("regate.manualEntrySail")}
                    value={manualSail}
                    onChange={(e) => setManualSail(e.target.value)}
                  />
                  <Button type="submit" disabled={!manualName.trim() || addManual.isPending}>
                    {t("regate.manualEntryAdd")}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setManualFormOpen(false);
                      setManualName("");
                      setManualSail("");
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                </form>
              </div>
            )}
          </div>

          {/* The link, not the bare code, is what actually gets pasted into the
              fleet's chat — so it is shown in full and copying it is the one
              filled button; rotating and revoking stay quiet icons. */}
          <div className={styles.share}>
            <span className="sf-field__label">{t("regate.joinCode")}</span>
            <p className={`sf-muted ${styles.shareHint}`}>{t("regate.joinCodeHint")}</p>
            {joinUrl ? (
              <>
                <code className={styles.link}>{joinUrl}</code>
                <div className={styles.shareActions}>
                  <Button onClick={copyLink} title={t("regate.copyJoinLink")}>
                    <Copy size={16} /> {t("regate.copyLink")}
                  </Button>
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("regate.regenerateJoinCode")}
                    title={t("regate.regenerateJoinCode")}
                    disabled={regenerate.isPending}
                    onClick={() => regenerate.mutate()}
                  >
                    <RefreshCw size={16} />
                  </Button>
                  <Button
                    variant="ghost"
                    className="sf-btn--icon-sm"
                    aria-label={t("regate.revokeJoinCode")}
                    title={t("regate.revokeJoinCode")}
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate()}
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>
              </>
            ) : (
              <Button
                className={styles.createCode}
                onClick={() => regenerate.mutate()}
                disabled={regenerate.isPending}
              >
                {t("regate.createJoinCode")}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
