import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { SessionDetail } from "@/components/session/SessionDetail";
import { Spinner } from "@/components/ui/Spinner";
import { BackLink } from "@/components/ui/BackLink";
import type { UUID } from "@/types";

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: UUID }>();
  const { t } = useTranslation();
  // Only fetched here for the BackLink's fallback target (whether this
  // session belongs to an activity) — SessionDetail fetches its own copy.
  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId!),
    queryFn: () => sessionsService.get(sessionId!),
    enabled: !!sessionId,
  });

  if (session.isLoading || !sessionId) return <Spinner />;
  if (!session.data) return null;

  return (
    <div className="sf-section__body">
      {session.data.activity_id && (
        <BackLink
          fallback={`/diario/activities/${session.data.activity_id}`}
          label={t("sessions.backToActivity")}
        />
      )}
      <SessionDetail sessionId={sessionId} variant="page" />
    </div>
  );
}
