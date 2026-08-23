import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, Sailboat, Radio, Users, UploadCloud, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { deviceKeys, devicesService } from "@/services/devices";
import { readCache, writeCache } from "@/services/offlineCache";
import { Section } from "@/components/ui/Section";
import styles from "./StartChecklist.module.css";

const DISMISSED_KEY = "start_checklist_dismissed";

interface Step {
  key: string;
  icon: typeof Sailboat;
  href: string;
  done: boolean;
}

/** First-run progress block on the personal diary: four steps that make the
 * app actually useful (boat, device, club/group, first outing), each linking
 * straight to the action. Boat/group state comes off `caps.memberships` —
 * already loaded with the session, no extra request; device state reuses the
 * same `deviceKeys.all` query as `ProfiloLayout`'s devices page; the "first
 * outing" step is passed in by `MyDiaryPage`, which already fetches the
 * personal feed this page renders, so nothing here re-fetches it. Disappears
 * for good once every step is done, or the user dismisses it (persisted in
 * localStorage, `sf_start_checklist_dismissed`). */
export function StartChecklist({
  hasRecordedSession,
  sessionsLoading,
}: {
  hasRecordedSession: boolean;
  sessionsLoading: boolean;
}) {
  const { t } = useTranslation();
  const { caps, status } = useAuth();

  const devicesQuery = useQuery({
    queryKey: deviceKeys.all,
    queryFn: devicesService.list,
    enabled: status === "authed",
  });

  const [dismissed, setDismissed] = useState(() => readCache<boolean>(DISMISSED_KEY) ?? false);

  const isLoading = status === "loading" || devicesQuery.isLoading || sessionsLoading;
  if (isLoading || dismissed || !caps) return null;

  const m = caps.memberships;
  const steps: Step[] = [
    { key: "boat", icon: Sailboat, href: "/profilo/barche", done: m.boatsOwner.length > 0 },
    {
      key: "device",
      icon: Radio,
      href: "/profilo/devices",
      done: (devicesQuery.data?.length ?? 0) > 0,
    },
    {
      key: "group",
      icon: Users,
      href: "/gruppi",
      done: m.clubsOwned.length > 0 || m.clubsMember.length > 0 || m.groups.length > 0,
    },
    { key: "session", icon: UploadCloud, href: "/registra", done: hasRecordedSession },
  ];

  if (steps.every((s) => s.done)) return null;

  const dismiss = () => {
    writeCache(DISMISSED_KEY, true);
    setDismissed(true);
  };

  return (
    <Section
      title={t("onboarding.checklist.title")}
      actions={
        <button
          type="button"
          className={styles.dismiss}
          onClick={dismiss}
          aria-label={t("onboarding.checklist.dismiss")}
          title={t("onboarding.checklist.dismiss")}
        >
          <X size={16} />
        </button>
      }
    >
      <div className="sf-strip">
        {steps.map((s) => {
          const Icon = s.icon;
          return (
            <div
              key={s.key}
              className={`sf-strip__item ${s.done ? "sf-strip__item--muted" : ""}`}
            >
              <span className={styles.label}>
                {s.done ? (
                  <CheckCircle2 size={18} className={styles.checkDone} aria-hidden />
                ) : (
                  <Circle size={18} aria-hidden />
                )}
                <Icon size={16} aria-hidden />
                {t(`onboarding.checklist.${s.key}.label`)}
              </span>
              {!s.done && (
                <Link to={s.href} className="sf-btn sf-btn--primary sf-btn--sm">
                  {t(`onboarding.checklist.${s.key}.cta`)}
                </Link>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
