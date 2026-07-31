import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { raceKeys, regattasService } from "@/services/races";
import { fmtPoints } from "@/utils/format";
import type { UUID } from "@/types";
import podium from "./podium.module.css";
import { podiumRankClass } from "./podium";
import styles from "./MyRegattaCard.module.css";

/** The sailor's own hook into the regatta: entered or not, where they stand,
 * and the way back into their last race. Everything else on the page is the
 * event; this is the one block that is about the person reading it. */
export function MyRegattaCard({
  regattaId,
  boatId,
}: {
  regattaId: UUID;
  /** The viewer's boat on this start list, or null if none of their boats is
   * entered — which flips the card into its "enter your boat" call to action. */
  boatId: UUID | null;
}) {
  const { t } = useTranslation();

  const standings = useQuery({
    queryKey: raceKeys.standings(regattaId),
    queryFn: () => regattasService.standings(regattaId),
    enabled: !!boatId,
  });

  if (!boatId) {
    return (
      <Card title={t("regate.yourRegatta")}>
        <p className="sf-muted">{t("regate.notEntered")}</p>
        <Link className="sf-btn sf-btn--primary" to={`/regate/${regattaId}/join`}>
          {t("regate.joinAction")}
        </Link>
      </Card>
    );
  }

  const row = standings.data?.standings.find((s) => s.boat.id === boatId);
  const sailed = row ? Object.keys(row.races).length : 0;
  // The standings' `races` array is the event's own order, so walking it
  // backwards finds the last race this boat actually has a result in.
  const lastRace = [...(standings.data?.races ?? [])].reverse().find((r) => row?.races[r.id]);

  return (
    <Card title={t("regate.yourRegatta")}>
      {sailed === 0 || !row ? (
        <p className="sf-muted">{t("regate.enteredNotRaced")}</p>
      ) : (
        <div className={styles.summary}>
          <div className={styles.rank}>
            <span className={`${podium.medal} ${podiumRankClass(row.rank)} ${styles.medal}`}>
              {row.rank}
            </span>
            <span className={styles.rankLabel}>{t("race.position")}</span>
          </div>
          <div className={styles.figures}>
            <span className={styles.boat}>{row.boat.name}</span>
            <span className="sf-muted">
              {t("regate.pointsValue", { points: fmtPoints(row.total) })} ·{" "}
              {t("regate.raceCount", { count: sailed })}
            </span>
          </div>
          {lastRace && (
            <Link className={styles.lastRace} to={`/diario/regate/race/${lastRace.id}`}>
              {t("regate.lastRace")}
              <ChevronRight size={16} />
            </Link>
          )}
        </div>
      )}
    </Card>
  );
}
