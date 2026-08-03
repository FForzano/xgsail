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
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import type { RegattaEntry, UUID } from "@/types";
import styles from "./RegattaEntries.module.css";

const NO_DIVISION = "__none__";

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
  const [addDivisionId, setAddDivisionId] = useState<UUID | typeof NO_DIVISION>(NO_DIVISION);
  const [manualName, setManualName] = useState("");
  const [manualSail, setManualSail] = useState("");
  const [manualDivisionId, setManualDivisionId] = useState<UUID | typeof NO_DIVISION>(NO_DIVISION);
  const [linkingEntryId, setLinkingEntryId] = useState<UUID | null>(null);
  const [linkBoatId, setLinkBoatId] = useState<UUID | "">("");
  const [manualFormOpen, setManualFormOpen] = useState(false);

  const entries = useQuery({
    queryKey: raceKeys.entries(regattaId),
    queryFn: () => regattasService.entries(regattaId),
  });
  const divisions = useQuery({
    queryKey: raceKeys.divisions(regattaId),
    queryFn: () => regattasService.divisions(regattaId),
  });
  const joinCode = useQuery({
    queryKey: raceKeys.joinCode(regattaId),
    queryFn: () => regattasService.joinCode(regattaId),
    enabled: manage,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: raceKeys.entries(regattaId) });
    await queryClient.invalidateQueries({ queryKey: raceKeys.standings(regattaId) });
  };
  const invalidateCode = () =>
    queryClient.invalidateQueries({ queryKey: raceKeys.joinCode(regattaId) });

  const add = useMutation({
    mutationFn: () =>
      regattasService.addEntry(
        regattaId,
        boatId as UUID,
        addDivisionId === NO_DIVISION ? null : addDivisionId,
      ),
    onSuccess: async () => {
      setBoatId("");
      setAddDivisionId(NO_DIVISION);
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });
  const addManual = useMutation({
    mutationFn: () =>
      regattasService.addManualEntry(
        regattaId,
        manualName.trim(),
        manualSail.trim() || null,
        manualDivisionId === NO_DIVISION ? null : manualDivisionId,
      ),
    onSuccess: async () => {
      setManualName("");
      setManualSail("");
      setManualDivisionId(NO_DIVISION);
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
  const setDivision = useMutation({
    mutationFn: ({ entryId, divisionId }: { entryId: UUID; divisionId: UUID | null }) =>
      regattasService.setEntryDivision(regattaId, entryId, divisionId),
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
  const divs = divisions.data ?? [];
  const code = joinCode.data?.join_code ?? null;
  const joinUrl = code ? `${publicWebOrigin}/regate/${regattaId}/join?code=${code}` : null;

  const copyLink = async () => {
    if (!joinUrl) return;
    await navigator.clipboard.writeText(joinUrl);
    notify(t("common.copied"), "success");
  };

  // Grouped by division, API order, unassigned (incl. a division that no
  // longer exists) last — only when the regatta has at least one division,
  // so a regatta without any renders exactly as the flat list did before.
  const knownDivisionIds = new Set(divs.map((d) => d.id));
  const groups: Array<{ id: UUID | null; name: string | null; rows: RegattaEntry[] }> =
    divs.length === 0
      ? [{ id: null, name: null, rows }]
      : [
          ...divs.map((d) => ({
            id: d.id,
            name: d.name,
            rows: rows.filter((r) => r.division_id === d.id),
          })),
          {
            id: null,
            name: t("regate.noDivision"),
            rows: rows.filter((r) => !r.division_id || !knownDivisionIds.has(r.division_id)),
          },
        ];

  const renderChip = (e: RegattaEntry) => (
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
      {manage && divs.length > 0 && (
        <div className={styles.divisionSelect}>
          <Select
            id={`entry-division-${e.id}`}
            label={t("regate.assignDivision")}
            value={e.division_id && knownDivisionIds.has(e.division_id) ? e.division_id : NO_DIVISION}
            disabled={setDivision.isPending}
            onChange={(ev) => {
              const value = ev.target.value;
              setDivision.mutate({ entryId: e.id, divisionId: value === NO_DIVISION ? null : value });
            }}
          >
            <option value={NO_DIVISION}>{t("regate.noDivision")}</option>
            {divs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </div>
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
  );

  return (
    <div>
      {rows.length === 0 ? (
        <EmptyState>{t("regate.noEntries")}</EmptyState>
      ) : divs.length === 0 ? (
        <div className={styles.boatGrid}>{rows.map(renderChip)}</div>
      ) : (
        groups.map(
          (g) =>
            g.rows.length > 0 && (
              <div key={g.id ?? "none"} className={styles.divisionGroup}>
                <h4 className={styles.divisionHeading}>
                  {g.name}
                  <span className={`sf-muted ${styles.divisionCount}`}>
                    {t("regate.divisionEntryCount", { count: g.rows.length })}
                  </span>
                </h4>
                <div className={styles.boatGrid}>{g.rows.map(renderChip)}</div>
              </div>
            ),
        )
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
            {divs.length > 0 && (
              <Select
                id="entry-division"
                label={t("regate.assignDivision")}
                value={addDivisionId}
                onChange={(e) => setAddDivisionId(e.target.value as UUID | typeof NO_DIVISION)}
              >
                <option value={NO_DIVISION}>{t("regate.noDivision")}</option>
                {divs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
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
                  {divs.length > 0 && (
                    <Select
                      id="entry-manual-division"
                      label={t("regate.assignDivision")}
                      value={manualDivisionId}
                      onChange={(e) => setManualDivisionId(e.target.value as UUID | typeof NO_DIVISION)}
                    >
                      <option value={NO_DIVISION}>{t("regate.noDivision")}</option>
                      {divs.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </Select>
                  )}
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
                      setManualDivisionId(NO_DIVISION);
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
