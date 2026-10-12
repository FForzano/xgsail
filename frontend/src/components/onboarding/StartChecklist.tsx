import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Sailboat, Radio, Users, UploadCloud, X } from "lucide-react";
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
  // Most useful first: an outing is what the whole app is for, and a phone
  // is enough to record one; a dedicated device is the optional step, last.
  const steps: Step[] = [
    { key: "session", icon: UploadCloud, href: "/registra", done: hasRecordedSession },
    { key: "boat", icon: Sailboat, href: "/profilo/barche", done: m.boatsOwner.length > 0 },
    {
      key: "group",
      icon: Users,
      href: "/gruppi",
      done: m.clubsOwned.length > 0 || m.clubsMember.length > 0 || m.groups.length > 0,
    },
    {
      key: "device",
      icon: Radio,
      href: "/profilo/devices",
      done: (devicesQuery.data?.length ?? 0) > 0,
    },
  ];

  if (steps.every((s) => s.done)) return null;

  const dismiss = () => {
    writeCache(DISMISSED_KEY, true);
    setDismissed(true);
  };

  // Only what is left to do is listed — finished steps collapse into the
  // count in the heading — and only the next step is a filled button, so the
  // block asks for one thing rather than four.
  const remaining = steps.filter((s) => !s.done);
  const doneCount = steps.length - remaining.length;

  return (
    <Section
      title={
        <>
          {t("onboarding.checklist.title")}{" "}
          <span className={styles.count}>
            {t("onboarding.checklist.progress", { done: doneCount, total: steps.length })}
          </span>
        </>
      }
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
        {remaining.map((s, index) => {
          const Icon = s.icon;
          return (
            <div key={s.key} className="sf-strip__item">
              <span className={styles.label}>
                <Icon size={16} aria-hidden />
                {t(`onboarding.checklist.${s.key}.label`)}
              </span>
              <Link
                to={s.href}
                className={`sf-btn sf-btn--sm ${index === 0 ? "sf-btn--primary" : "sf-btn--ghost"}`}
              >
                {t(`onboarding.checklist.${s.key}.cta`)}
              </Link>
            </div>
          );
        })}
      </div>
    </Section>
  );
}
