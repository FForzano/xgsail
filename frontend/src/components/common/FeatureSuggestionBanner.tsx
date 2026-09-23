import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Lightbulb } from "lucide-react";
import { CONTACT_EMAIL } from "@/config/links";
import { SlimBanner } from "@/components/common/SlimBanner";

const FIRST_SEEN_KEY = "xgsail.featureSuggestion.firstSeenAt";
const NEXT_ELIGIBLE_KEY = "xgsail.featureSuggestion.nextEligibleAt";
const FIRST_DELAY_MS = 14 * 24 * 60 * 60 * 1000;
const SNOOZE_MS = 60 * 24 * 60 * 60 * 1000;

function readNumber(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

function writeNumber(key: string, value: number) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // best-effort only
  }
}

function isDue(): boolean {
  const now = Date.now();
  let firstSeen = readNumber(FIRST_SEEN_KEY);
  if (firstSeen === null) {
    firstSeen = now;
    writeNumber(FIRST_SEEN_KEY, firstSeen);
  }
  const nextEligible = readNumber(NEXT_ELIGIBLE_KEY) ?? firstSeen + FIRST_DELAY_MS;
  return now >= nextEligible;
}

/** Periodic nudge to suggest a feature or report an issue. Client-only
 * cadence (localStorage, best-effort) — unlike SupportPromptBanner there's
 * no backend capability to key this off, and a low-stakes prompt like this
 * doesn't warrant adding one. First shown 14 days after first seen, snoozed
 * 60 days after each dismissal — deliberately shorter/less sticky than the
 * donation reminder's 30/45-day backend cadence, since asking for feedback
 * is a lighter ask than asking for money. Shown on every platform (unlike
 * InstallAppBanner) — there's nothing Android-specific about it. */
export function FeatureSuggestionBanner() {
  const { t } = useTranslation();
  const [show, setShow] = useState(isDue);

  if (!show) return null;

  const dismiss = () => {
    writeNumber(NEXT_ELIGIBLE_KEY, Date.now() + SNOOZE_MS);
    setShow(false);
  };

  const subject = encodeURIComponent(t("featureSuggestion.subject"));

  return (
    <SlimBanner
      tint="primary"
      icon={<Lightbulb size={16} />}
      text={t("featureSuggestion.text")}
      ctaLabel={t("featureSuggestion.cta")}
      ctaHref={`mailto:${CONTACT_EMAIL}?subject=${subject}`}
      onCtaClick={dismiss}
      onDismiss={dismiss}
      dismissLabel={t("featureSuggestion.dismiss")}
    />
  );
}
