import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { BackLink } from "@/components/ui/BackLink";
import { Section } from "@/components/ui/Section";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { userLabel } from "@/utils/format";
import type { BoatClaimStatus, ClaimableBoat, UUID } from "@/types";
import styles from "./ClaimBoatPage.module.css";

function claimStatusBadge(status: BoatClaimStatus): string {
  return status === "approved"
    ? "sf-badge sf-badge--success"
    : status === "rejected"
      ? "sf-badge sf-badge--danger"
      : "sf-badge sf-badge--warning";
}

const CLAIM_STATUS_LABEL: Record<BoatClaimStatus, "claimPending" | "claimApproved" | "claimRejected"> = {
  pending: "claimPending",
  approved: "claimApproved",
  rejected: "claimRejected",
};

function apiErrorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : err instanceof Error ? err.message : fallback;
}

export function ClaimBoatPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<ClaimableBoat | null>(null);

  const trimmed = query.trim();
  const results = useQuery({
    queryKey: boatKeys.claimable(trimmed),
    queryFn: () => boatsService.listClaimable(trimmed),
    enabled: trimmed.length >= 2,
  });

  const myBoats = useQuery({
    queryKey: boatKeys.mine,
    queryFn: () => boatsService.list(true),
  });

  const outgoing = useQuery({ queryKey: boatKeys.claimsMine, queryFn: boatsService.listMyClaims });

  return (
    <div className="sf-section__body">
      <BackLink to="/profilo/barche" label={t("noteTemplates.backToBoats")} />

      <Section title={t("boats.claimTitle")}>
        <p className="sf-muted">{t("boats.claimIntro")}</p>
        <div className={styles.searchRow}>
          <InputField
            label={t("boats.claimSearchPlaceholder")}
            id="claim-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("boats.claimSearchPlaceholder")}
          />
        </div>

        {trimmed.length >= 2 &&
          (results.isLoading ? (
            <Spinner />
          ) : results.data?.length === 0 ? (
            <EmptyState>{t("boats.claimNoResults")}</EmptyState>
          ) : (
            <div className="sf-strip">
              {results.data?.map((b) => (
                <div key={b.id} className={`sf-strip__item ${styles.result}`}>
                  <div className={styles.resultMain}>
                    <strong>{b.name}</strong>
                    <span className={`sf-muted ${styles.resultMeta}`}>
                      <span>{b.sail_number ?? "—"}</span>
                      <span>{b.boat_class ?? "—"}</span>
                      <span>{b.session_count}</span>
                    </span>
                    {b.created_by && (
                      <span className="sf-muted">
                        {t("boats.claimCreatedBy", { name: userLabel(b.created_by) })}
                      </span>
                    )}
                  </div>
                  <Button className="sf-btn--sm" onClick={() => setTarget(b)}>
                    {t("boats.claimSubmit")}
                  </Button>
                </div>
              ))}
            </div>
          ))}
      </Section>

      <Section title={t("boats.claimsOutgoing")}>
        {outgoing.isLoading ? (
          <Spinner />
        ) : outgoing.data?.length === 0 ? (
          <EmptyState>{t("boats.claimsOutgoingEmpty")}</EmptyState>
        ) : (
          <div className="sf-strip">
            {outgoing.data?.map((c) => (
              <div key={c.id} className="sf-strip__item">
                <span>{c.boat?.name ?? "—"}</span>
                <span className={claimStatusBadge(c.status)}>{t(`boats.${CLAIM_STATUS_LABEL[c.status]}`)}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      {target && (
        <ClaimBoatModal
          boat={target}
          myBoats={(myBoats.data ?? []).filter((b) => !b.is_guest && b.id !== target.id)}
          onClose={() => setTarget(null)}
          onSubmitted={async () => {
            setTarget(null);
            await queryClient.invalidateQueries({ queryKey: boatKeys.claimsMine });
            notify(t("boats.claimSent"), "success");
          }}
          onFailed={(err) => notify(apiErrorMessage(err, t("boats.claimFailed")), "error")}
        />
      )}
    </div>
  );
}

function ClaimBoatModal({
  boat,
  myBoats,
  onClose,
  onSubmitted,
  onFailed,
}: {
  boat: ClaimableBoat;
  myBoats: { id: UUID; name: string }[];
  onClose: () => void;
  onSubmitted: () => Promise<void>;
  onFailed: (err: unknown) => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"new" | "merge">("new");
  const [mergeInto, setMergeInto] = useState<UUID | "">("");

  const submit = useMutation({
    mutationFn: () => boatsService.createClaim(boat.id, mode === "merge" ? (mergeInto || null) : null),
    onSuccess: onSubmitted,
    onError: onFailed,
  });

  const canSubmit = mode === "new" || !!mergeInto;

  return (
    <Modal title={boat.name} onClose={onClose}>
      <div className={styles.modeChoice}>
        <label className={styles.modeOption}>
          <input
            type="radio"
            name="claim-mode"
            checked={mode === "new"}
            onChange={() => setMode("new")}
          />
          <span>
            <strong>{t("boats.claimAsNew")}</strong>
            <p className="sf-muted">{t("boats.claimAsNewHint")}</p>
          </span>
        </label>
        <label className={styles.modeOption}>
          <input
            type="radio"
            name="claim-mode"
            checked={mode === "merge"}
            onChange={() => setMode("merge")}
          />
          <span>
            <strong>{t("boats.claimMergeInto")}</strong>
            <p className="sf-muted">{t("boats.claimMergeIntoHint")}</p>
          </span>
        </label>
      </div>

      {mode === "merge" && (
        <>
          <Select
            label={t("boats.claimMergeInto")}
            id="claim-merge-target"
            value={mergeInto}
            onChange={(e) => setMergeInto(e.target.value as UUID)}
          >
            <option value="">—</option>
            {myBoats.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
          <p className="sf-badge sf-badge--warning">{t("boats.claimMergeWarning")}</p>
        </>
      )}

      <div className="sf-form__actions">
        <Button variant="ghost" onClick={onClose} disabled={submit.isPending}>
          {t("common.cancel")}
        </Button>
        <Button onClick={() => submit.mutate()} disabled={!canSubmit || submit.isPending}>
          {t("boats.claimSubmit")}
        </Button>
      </div>
    </Modal>
  );
}
