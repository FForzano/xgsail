import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { useToast } from "@/hooks/useToast";

/** Shared by every "link this club to an OSM element" mutation (ClubsPage's
 * arrive-from-map flow, ClubOverview's own-page suggestions). A 409 has one
 * specific, actionable cause — the element got linked to another club first
 * — everything else is generic. */
export function useOsmLinkErrorNotifier() {
  const { t } = useTranslation();
  const { notify } = useToast();

  return (error: unknown) =>
    notify(
      error instanceof ApiError && error.status === 409
        ? t("gruppi.osmAlreadyLinked")
        : t("errors.generic"),
      "error",
    );
}
