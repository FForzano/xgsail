import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { sessionsService, sessionKeys } from "@/services/sessions";
import { SessionDetail } from "@/components/session/SessionDetail";
import { Spinner } from "@/components/ui/Spinner";
import type { UUID } from "@/types";

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: UUID }>();
  const { t } = useTranslation();
  // Only fetched here for the way back's fallback target (whether this
  // session belongs to an activity) — SessionDetail fetches its own copy.
  const session = useQuery({
    queryKey: sessionKeys.detail(sessionId!),
    queryFn: () => sessionsService.get(sessionId!),
    enabled: !!sessionId,
  });

  if (session.isLoading || !sessionId) return <Spinner />;
  if (!session.data) return null;

  // SessionDetail renders the way back itself: an icon in its pinned title bar
  // on a phone, a link above the title on a wide screen.
  return (
    <SessionDetail
      sessionId={sessionId}
      variant="page"
      back={{
        fallback: session.data.activity_id ? `/diario/activities/${session.data.activity_id}` : "/diario/personale",
        label: t("sessions.backToActivity"),
      }}
    />
  );
}
