import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Bluetooth, Download, Radio, ShieldCheck, Smartphone, CheckCircle2, Lightbulb } from "lucide-react";
import { useTranslation } from "react-i18next";
import { isNativeApp } from "@/config/platform";
import { ANDROID_APK_URL, CONTACT_EMAIL } from "@/config/links";
import { isAndroidUserAgent } from "@/utils/userAgent";
import { BottomSheet } from "@/components/ui/BottomSheet";
import { Button } from "@/components/ui/Button";
import { Carousel } from "@/components/ui/Carousel";
import { SlimBanner } from "@/components/common/SlimBanner";
import { SupportLink } from "@/components/common/SupportLink";
import styles from "./InstallAppBanner.module.css";

const DISMISSED_KEY = "xgsail.installAppBanner.dismissed";

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

// What the native app has that the mobile browser doesn't. `image` is
// optional and swappable independently per feature — set/change it to any
// path under frontend/public/ (currently reusing two of the landing page's
// own screenshots as placeholders); a feature with no image falls back to
// its icon. See i18n installPrompt.feature{1,2,3}{Title,Body} for the copy.
const FEATURES: { key: string; image?: string; Icon: LucideIcon }[] = [
  { key: "feature1", image: "/landing/record.png", Icon: Smartphone },
  { key: "feature2", image: "/landing/devices.png", Icon: Bluetooth },
  { key: "feature3", Icon: Radio },
];

const STEPS: { key: string; Icon: LucideIcon }[] = [
  { key: "step1", Icon: Download },
  { key: "step2", Icon: ShieldCheck },
  { key: "step3", Icon: CheckCircle2 },
];

/** Dismissible nudge toward the native Android app, shown only to Android
 * mobile-browser visitors (never inside the native app itself, never on
 * iOS/desktop — there's nothing to sideload there yet). Dismissal is a plain
 * localStorage flag: unlike SupportPromptBanner this has no cross-device
 * cadence to enforce, so there's no need for backend-tracked state. */
export function InstallAppBanner() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(readDismissed);
  const [sheetOpen, setSheetOpen] = useState(false);

  if (isNativeApp || dismissed || !isAndroidUserAgent()) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // best-effort only
    }
    setDismissed(true);
  };

  const suggestSubject = encodeURIComponent(t("installPrompt.suggestSubject"));

  return (
    <>
      <SlimBanner
        tint="primary"
        icon={<Smartphone size={16} />}
        text={t("installPrompt.banner")}
        ctaLabel={t("installPrompt.cta")}
        onCtaClick={() => setSheetOpen(true)}
        onDismiss={dismiss}
        dismissLabel={t("installPrompt.dismiss")}
      />
      <BottomSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title={t("installPrompt.sheetTitle")}
        footer={
          <a href={ANDROID_APK_URL} className={styles.downloadLink} onClick={dismiss}>
            <Button variant="primary" className={styles.downloadButton}>
              <Download size={16} strokeWidth={2} /> {t("installPrompt.download")}
            </Button>
          </a>
        }
      >
        <p className={styles.sheetIntro}>{t("installPrompt.whyNotStore")}</p>

        <h3 className={styles.sectionHeading}>{t("installPrompt.featuresHeading")}</h3>
        <Carousel>
          {FEATURES.map(({ key, image, Icon }) => (
            <div className={styles.slideContent} key={key}>
              {image ? (
                <img src={image} alt="" className={styles.slideImage} />
              ) : (
                <div className={styles.slideIcon}>
                  <Icon size={28} strokeWidth={1.5} aria-hidden />
                </div>
              )}
              <h4 className={styles.slideTitle}>{t(`installPrompt.${key}Title`)}</h4>
              <p className={styles.slideBody}>{t(`installPrompt.${key}Body`)}</p>
            </div>
          ))}
        </Carousel>

        <h3 className={styles.sectionHeading}>{t("installPrompt.stepsHeading")}</h3>
        <Carousel>
          {STEPS.map(({ key, Icon }, i) => (
            <div className={styles.slideContent} key={key}>
              <div className={styles.slideIcon}>
                <Icon size={28} strokeWidth={1.5} aria-hidden />
              </div>
              <h4 className={styles.slideTitle}>
                {i + 1}. {t(`installPrompt.${key}Title`)}
              </h4>
              <p className={styles.slideBody}>{t(`installPrompt.${key}Body`)}</p>
            </div>
          ))}
        </Carousel>

        <div className={styles.invites}>
          <p className={styles.inviteLine}>
            <SupportLink className={styles.inviteLink} /> {t("installPrompt.supportBody")}
          </p>
          <p className={styles.inviteLine}>
            <Lightbulb size={14} className={styles.inviteIcon} aria-hidden />
            <a
              href={`mailto:${CONTACT_EMAIL}?subject=${suggestSubject}`}
              className={styles.inviteLink}
            >
              {t("installPrompt.suggestCta")}
            </a>{" "}
            {t("installPrompt.suggestBody")}
          </p>
        </div>
      </BottomSheet>
    </>
  );
}
