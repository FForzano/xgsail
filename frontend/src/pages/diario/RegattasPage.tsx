import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { racedaysService, regattasService, raceKeys } from "@/services/races";
import { clubsService, clubKeys } from "@/services/clubs";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { fmtDate } from "@/utils/format";
import type { UUID } from "@/types";

function RegattaRaces({ regattaId }: { regattaId: UUID }) {
  const { t } = useTranslation();
  const regatta = useQuery({
    queryKey: raceKeys.regatta(regattaId),
    queryFn: () => regattasService.get(regattaId),
  });
  if (regatta.isLoading) return <Spinner />;
  const days = regatta.data?.race_days ?? [];
  if (!days.length) return <p className="sf-muted">{t("common.none")}</p>;
  return (
    <div className="sf-strip">
      {days.map((day) => (
        <DayRaces key={day.id} dayId={day.id} date={day.date} />
      ))}
    </div>
  );
}

function DayRaces({ dayId, date }: { dayId: UUID; date: string }) {
  const { t } = useTranslation();
  const day = useQuery({
    queryKey: raceKeys.raceday(dayId),
    queryFn: () => racedaysService.get(dayId),
  });
  return (
    <div className="sf-strip__item sf-strip__item--muted" style={{ flexWrap: "wrap" }}>
      <span>
        <strong>{fmtDate(date)}</strong>
      </span>
      <span className="sf-strip__actions" style={{ flexWrap: "wrap" }}>
        {(day.data?.races ?? []).map((r) => (
          <Link key={r.id} to={`/diario/regate/race/${r.id}`}>
            <Button variant="ghost" className="sf-btn--sm">
              {t("regate.raceNumber")} {r.race_number}
            </Button>
          </Link>
        ))}
      </span>
    </div>
  );
}

export function RegattasPage() {
  const { t } = useTranslation();
  const [open, setOpen] = useState<UUID | null>(null);

  const regattas = useQuery({ queryKey: raceKeys.regattas, queryFn: () => regattasService.list() });
  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });

  if (regattas.isLoading) return <Spinner />;

  const clubName = (id: UUID) => clubs.data?.find((c) => c.id === id)?.name ?? "—";

  return (
    <Card title={t("regate.title")}>
      {regattas.data?.length === 0 ? (
        <EmptyState>{t("regate.empty")}</EmptyState>
      ) : (
        <div className="sf-strip">
          {regattas.data?.map((r) => (
            <div key={r.id}>
              <div className="sf-strip__item">
                <span>
                  <strong>{r.name}</strong>{" "}
                  <span className="sf-muted">
                    {clubName(r.club_id)} · {fmtDate(r.start_date)}
                  </span>
                </span>
                <Button
                  variant="ghost"
                  className="sf-btn--sm"
                  onClick={() => setOpen(open === r.id ? null : r.id)}
                >
                  {open === r.id ? t("common.close") : t("regate.races")}
                </Button>
              </div>
              {open === r.id && <RegattaRaces regattaId={r.id} />}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
