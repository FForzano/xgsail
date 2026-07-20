import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { UUID } from "@/types";
import { useDiaryFeed } from "@/hooks/useDiaryFeed";
import { EventRow } from "@/components/diario/EventRow";
import { DiaryToolbar } from "@/components/diario/DiaryToolbar";
import feedStyles from "@/components/diario/EventRow.module.css";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

/** "Circoli e gruppi" diario tab: activities + regattas of every club/group
 * the current user actively belongs to. Public activities of clubs/groups
 * they DON'T belong to intentionally stay out of this list — those are only
 * reachable from that club's own Eventi tab (`ClubEvents.tsx`). Same
 * `.page`/toolbar shell as `MyDiaryPage`, just without the import action,
 * so the two tabs read as one consistent layout. */
export function ClubsDiaryPage() {
  const { t } = useTranslation();
  const { type, setType, items, isLoading, hasNextPage, sentinelRef } = useDiaryFeed("clubs", t);
  const [openRegattaId, setOpenRegattaId] = useState<UUID | null>(null);

  return (
    <div className={feedStyles.page}>
      <DiaryToolbar type={type} onTypeChange={setType} />

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
  );
}
