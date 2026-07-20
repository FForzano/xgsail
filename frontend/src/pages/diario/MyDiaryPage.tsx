import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { UUID } from "@/types";
import { useDiaryFeed } from "@/hooks/useDiaryFeed";
import { UpcomingEventsBanner } from "@/components/diario/UpcomingEventsBanner";
import { EventRow } from "@/components/diario/EventRow";
import { DiaryToolbar } from "@/components/diario/DiaryToolbar";
import feedStyles from "@/components/diario/EventRow.module.css";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

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

  return (
    <>
      <UpcomingEventsBanner />
      <div className={feedStyles.page}>
        <DiaryToolbar type={type} onTypeChange={setType} importHref="/diario/activities/import" />

        {isLoading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <EmptyState>{t("activities.empty")}</EmptyState>
        ) : (
          <>
            <div className={feedStyles.feed}>
              {items.map((i) => (
                <EventRow
                  key={`${i.kind}-${i.id}`}
                  item={i}
                  manage={false}
                  open={openRegattaId === i.id}
                  onToggle={() => setOpenRegattaId(openRegattaId === i.id ? null : i.id)}
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
