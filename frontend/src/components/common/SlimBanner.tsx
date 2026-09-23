import type { ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./SlimBanner.module.css";

/** Shared shape for the dismissible bars mounted at the top of AppShell —
 * icon, one line of text, a CTA, a dismiss "X". Extracted once a third
 * consumer (FeatureSuggestionBanner, alongside SupportPromptBanner and
 * InstallAppBanner) needed the exact same layout, instead of copying the
 * CSS a third time. */
export function SlimBanner({
  icon,
  text,
  ctaLabel,
  ctaHref,
  ctaTarget,
  onCtaClick,
  onDismiss,
  dismissLabel,
  tint = "primary",
}: {
  icon: ReactNode;
  text: ReactNode;
  ctaLabel: string;
  /** Omit for a CTA that performs an action (e.g. opening a sheet) instead of navigating. */
  ctaHref?: string;
  ctaTarget?: "_blank";
  onCtaClick?: () => void;
  onDismiss: () => void;
  dismissLabel: string;
  tint?: "primary" | "warning";
}) {
  return (
    <div className={`${styles.banner} ${styles[tint]}`} role="note">
      <span className={styles.icon} aria-hidden>
        {icon}
      </span>
      <span className={styles.text}>{text}</span>
      {ctaHref ? (
        <a
          href={ctaHref}
          target={ctaTarget}
          rel={ctaTarget ? "noreferrer" : undefined}
          className={styles.cta}
          onClick={onCtaClick}
        >
          {ctaLabel}
        </a>
      ) : (
        <button type="button" className={styles.cta} onClick={onCtaClick}>
          {ctaLabel}
        </button>
      )}
      <button
        type="button"
        className={styles.dismiss}
        onClick={onDismiss}
        aria-label={dismissLabel}
        title={dismissLabel}
      >
        <X size={16} />
      </button>
    </div>
  );
}
