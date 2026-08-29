import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { UUID } from "@/types";
import { useDiaryFeed } from "@/hooks/useDiaryFeed";
import { LiveRecordingBanner } from "@/components/diario/LiveRecordingBanner";
import { UpcomingEventsBanner } from "@/components/diario/UpcomingEventsBanner";
import { EventRow } from "@/components/diario/EventRow";
import { DiaryToolbar } from "@/components/diario/DiaryToolbar";
import feedStyles from "@/components/diario/EventRow.module.css";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { TourDemoCard } from "@/onboarding/TourDemoCard";
import { useOnboarding } from "@/onboarding/OnboardingContext";
import { StartChecklist } from "@/components/onboarding/StartChecklist";
import { ProgressStrip } from "@/components/diario/ProgressStrip";
import { useProgress } from "@/hooks/useProgress";

/** "Personale" diario tab: my own activities plus regattas I've actually
 * raced in (a personal `created_by` doesn't exist for regattas, so "mine"
 * there means having a result/crew tie, resolved backend-side via
 * `?mine=true`). No `Card` wrapper here — the tab bar above already labels
 * this page, so a big "Le mie attività" title block repeating it would just
 * be another layer of nesting. */
export function MyDiaryPage() {
  const { t } = useTranslation();
  const { type, setType, items, isLoading, hasNextPage, sentinelRef } = useDiaryFeed("personal", t);
  const [openRegattaId, setOpenRegattaId] = useState<UUID | null>(null);
  const { isDemoTarget } = useOnboarding();
  // One or the other above the feed, never both: the start checklist can
  // persist indefinitely (its "join a club" step may never be done by a solo
  // sailor), and stacking it under the progress strip is exactly the clutter
  // this arbitration avoids. Three outings means onboarding is behind us;
  // while the query is still loading the page looks like it does today.
  const progress = useProgress();
  const showProgress = (progress.data?.totals.sessions ?? 0) >= 3;

  return (
    <>
      <div className={feedStyles.page}>
        {/* Above the "in arrivo" strip: an outing happening right now is the
            one thing on this page that stops being actionable if missed. */}
        <LiveRecordingBanner />
        <UpcomingEventsBanner />
        <DiaryToolbar type={type} onTypeChange={setType} importHref="/diario/activities/import" />
        {showProgress ? (
          <ProgressStrip />
        ) : (
          <StartChecklist hasRecordedSession={items.length > 0} sessionsLoading={isLoading} />
        )}

        {isLoading ? (
          <Spinner />
        ) : items.length === 0 ? (
          // While the "your sessions land here" tour step is active on an
          // otherwise-empty feed, show a demo card so the step has something
          // to frame; it disappears the moment the tour moves on.
          isDemoTarget("diario-feed") ? (
            <div className={feedStyles.feed}>
              <TourDemoCard dataTour="diario-feed" />
            </div>
          ) : (
            <EmptyState>{t("activities.empty")}</EmptyState>
          )
        ) : (
          <>
            <div className={feedStyles.feed}>
              {items.map((i, index) => (
                <EventRow
                  key={`${i.kind}-${i.id}`}
                  item={i}
                  manage={false}
                  open={openRegattaId === i.id}
                  onToggle={() => setOpenRegattaId(openRegattaId === i.id ? null : i.id)}
                  // Anchors the guided-tour "your activities" step to a
                  // single card instead of the whole (potentially very
                  // tall) feed — see onboarding/tours.ts.
                  dataTour={index === 0 ? "diario-feed" : undefined}
                />
              ))}
            </div>
            {hasNextPage && (
              <div ref={sentinelRef} className="sf-activity-grid__sentinel">
                <Spinner />
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
