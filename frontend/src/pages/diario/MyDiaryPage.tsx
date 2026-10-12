import { useTranslation } from "react-i18next";
import { Fragment, useState } from "react";
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
import { Notice } from "@/components/ui/Notice";
import { Button } from "@/components/ui/Button";

/** "Personale" diario tab: my own activities plus regattas I've actually
 * raced in (a personal `created_by` doesn't exist for regattas, so "mine"
 * there means having a result/crew tie, resolved backend-side via
 * `?mine=true`). No `Card` wrapper here — the tab bar above already labels
 * this page, so a big "Le mie attività" title block repeating it would just
 * be another layer of nesting. */
export function MyDiaryPage() {
  const { t } = useTranslation();
  const { type, setType, items, isLoading, isError, refetch, hasNextPage, sentinelRef } = useDiaryFeed(
    "personal",
    t,
  );
  const [openRegattaId, setOpenRegattaId] = useState<UUID | null>(null);
  const { isDemoTarget } = useOnboarding();
  // One or the other above the feed, never both: the start checklist can
  // persist indefinitely (its "join a club" step may never be done by a solo
  // sailor), and stacking it under the progress strip is exactly the clutter
  // this arbitration avoids. Three outings means onboarding is behind us;
  // while the query is still loading the page looks like it does today.
  const progress = useProgress();
  const showProgress = (progress.data?.totals.sessions ?? 0) >= 3;
  // Once there is an outing, it leads the page and the remaining setup steps
  // follow it: a checklist above the latest outing pushed its numbers off the
  // first screen, for the one sailor who no longer needs onboarding first.
  const checklistAfterHero = !showProgress && items.length > 0;
  // A failed load says nothing about what the sailor has done, so the
  // checklist (which would offer "record your first outing") waits it out.
  const showChecklist = !isError;

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
          showChecklist &&
          !checklistAfterHero && (
            <StartChecklist hasRecordedSession={items.length > 0} sessionsLoading={isLoading} />
          )
        )}

        {isError && <FeedErrorNotice stale={items.length > 0} onRetry={refetch} />}
        {isLoading ? (
          <Spinner />
        ) : isError && items.length === 0 ? null : items.length === 0 ? (
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
                <Fragment key={`${i.kind}-${i.id}`}>
                  <EventRow
                    item={i}
                    manage={false}
                    open={openRegattaId === i.id}
                    onToggle={() => setOpenRegattaId(openRegattaId === i.id ? null : i.id)}
                    // Anchors the guided-tour "your activities" step to a
                    // single card instead of the whole (potentially very
                    // tall) feed — see onboarding/tours.ts.
                    dataTour={index === 0 ? "diario-feed" : undefined}
                    featured={index === 0 && i.kind === "activity" && !!i.activity.summary}
                  />
                  {index === 0 && checklistAfterHero && showChecklist && (
                    <StartChecklist hasRecordedSession sessionsLoading={false} />
                  )}
                </Fragment>
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

/** The feed couldn't be loaded (marinas are often offline). With nothing
 * cached it must not fall through to "no outings"; with an older page still on
 * screen it says the list may be out of date. TanStack Query refetches on its
 * own when the connection returns, so offline needs no action — the retry is
 * for a server error. */
function FeedErrorNotice({ stale, onRetry }: { stale: boolean; onRetry: () => void }) {
  const { t } = useTranslation();
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  const key = offline ? "offline" : stale ? "stale" : "failed";
  return (
    <div className={feedStyles.notice}>
      <Notice
        title={t(`diario.feedError.${key}.title`)}
        body={t(`diario.feedError.${key}.body`)}
        live={offline}
        action={
          !offline && (
            <Button variant="ghost" onClick={onRetry}>
              {t("common.retry")}
            </Button>
          )
        }
      />
    </div>
  );
}
