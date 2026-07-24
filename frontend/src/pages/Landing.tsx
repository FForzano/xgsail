import { Navigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Apple,
  Download,
  Smartphone,
  Cpu,
  Satellite,
  Sun,
  Radio,
  UploadCloud,
  Power,
  Code2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { isNativeApp } from "@/config/platform";
import { SelfHostedArt } from "@/components/landing/FeatureArt";
import { SupportLink } from "@/components/common/SupportLink";
import {
  ANDROID_APK_URL,
  GITHUB_URL,
  LICENSE_URL,
  UPSTREAM_URL,
  CONTACT_EMAIL,
  E1_REPO_URL,
} from "@/config/links";
import styles from "@/components/landing/landing.module.css";

// Real product screenshots for features 1-6 — feature 7 (self-hosted) has no
// single app screen to show, so it keeps a stylized illustration instead.
const FEATURE_SHOTS: Record<number, string> = {
  1: "/landing/record.png",
  2: "/landing/playback.png",
  3: "/landing/analysis.png",
  4: "/landing/race.png",
  5: "/landing/clubs.png",
  6: "/landing/devices.png",
};
const FEATURE_KEYS = [1, 2, 3, 4, 5, 6, 7] as const;

const E1_HIGHLIGHTS: { key: string; Icon: LucideIcon }[] = [
  { key: "sensors", Icon: Satellite },
  { key: "display", Icon: Sun },
  { key: "mesh", Icon: Radio },
  { key: "upload", Icon: UploadCloud },
  { key: "power", Icon: Power },
  { key: "openHardware", Icon: Code2 },
];

/**
 * Public "/" route. Web: marketing page for anonymous visitors, redirects
 * authed users straight to the app. Native app builds have no anonymous
 * landing at all — there's no one to market to on a device the user already
 * installed the app on — so they skip straight to /login.
 */
export function LandingPage() {
  const { t } = useTranslation();
  const { status } = useAuth();

  if (status === "loading") return <Spinner full />;
  if (status === "authed") return <Navigate to="/diario/personale" replace />;
  if (isNativeApp) return <Navigate to="/login" replace />;

  return (
    <div className={styles.landing}>
      <div className={styles.supportBanner}>
        <span>☕ {t("support.summary")}</span>
        <SupportLink className={styles.supportBannerLink} />
      </div>

      <header className={styles.nav}>
        <Link to="/" className="sf-navbar__brand">
          <img src="/logo.svg" alt="" className="sf-navbar__logo" />
          <span className={styles.brandText}>
            <span>XGSail</span>
            <span className={styles.brandTagline}>{t("common.tagline")}</span>
          </span>
        </Link>
        <div className={styles.navActions}>
          <Link to="/login" className="sf-navlink">
            {t("auth.login")}
          </Link>
          <Link to="/register">
            <Button variant="ghost" className="sf-btn--sm">
              {t("landing.getStarted")}
            </Button>
          </Link>
        </div>
      </header>

      <main className={styles.hero}>
        <p className={styles.eyebrow}>{t("common.tagline")}</p>
        <h1 className={styles.title}>{t("landing.heroTitle")}</h1>
        <p className={styles.tagline}>{t("landing.heroSubtitle")}</p>
        <div className={styles.cta}>
          <Link to="/register">
            <Button>{t("landing.getStarted")}</Button>
          </Link>
          <Link to="/login">
            <Button variant="ghost">{t("auth.login")}</Button>
          </Link>
        </div>
      </main>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("landing.insightsTitle")}</h2>
        <div className={styles.features}>
          {FEATURE_KEYS.map((n) => (
            <div className="sf-card" key={n}>
              {FEATURE_SHOTS[n] ? (
                <img src={FEATURE_SHOTS[n]} alt="" className={styles.shot} />
              ) : (
                <SelfHostedArt />
              )}
              <h3 className="sf-card__title">{t(`landing.feature${n}Title`)}</h3>
              <p className="sf-muted">{t(`landing.feature${n}Body`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("landing.nativeAppsTitle")}</h2>
        <p className={`sf-muted ${styles.nativeAppsIntro}`}>{t("landing.nativeAppsIntro")}</p>
        <div className={styles.nativeApps}>
          <div className="sf-card">
            <Smartphone className={styles.nativeAppIcon} aria-hidden />
            <h3 className="sf-card__title">{t("landing.androidTitle")}</h3>
            <p className="sf-muted">{t("landing.androidBody")}</p>
            <a href={ANDROID_APK_URL}>
              <Button variant="ghost" className="sf-btn--sm">
                <Download size={16} strokeWidth={2} /> {t("landing.androidDownload")}
              </Button>
            </a>
          </div>
          <div className="sf-card">
            <Apple className={styles.nativeAppIcon} aria-hidden />
            <h3 className="sf-card__title">{t("landing.iosTitle")}</h3>
            <p className="sf-muted">{t("landing.iosBody")}</p>
          </div>
        </div>
        <p className={`sf-muted ${styles.nativeAppsNote}`}>
          {t("landing.nativeAppsNote")} {t("landing.nativeAppsDonatePrompt")}{" "}
          <SupportLink className={styles.nativeAppsDonateLink} />
        </p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>{t("landing.e1Title")}</h2>
        <div className={`sf-card ${styles.e1Card}`}>
          <div className={styles.e1Head}>
            <span className={styles.e1IconWrap}>
              <Cpu size={28} strokeWidth={2} aria-hidden />
            </span>
            <div>
              <h3 className="sf-card__title">{t("landing.e1CardTitle")}</h3>
              <p className="sf-muted">{t("landing.e1Body")}</p>
            </div>
            <img
              src="/devices/e1-display-modes/d2.png"
              alt={t("landing.e1ShotAlt")}
              className={styles.e1Shot}
            />
          </div>
          <div className={styles.e1Highlights}>
            {E1_HIGHLIGHTS.map(({ key, Icon }) => (
              <div className={styles.e1Highlight} key={key}>
                <Icon size={18} strokeWidth={2} className={styles.e1HighlightIcon} aria-hidden />
                <span>{t(`landing.e1Highlights.${key}`)}</span>
              </div>
            ))}
          </div>
          <a href={E1_REPO_URL} target="_blank" rel="noreferrer" className={styles.e1Cta}>
            <Button variant="ghost" className="sf-btn--sm">
              {t("landing.e1RepoLink")}
            </Button>
          </a>
        </div>
      </section>

      <footer className={styles.footer}>
        <p className={`sf-muted ${styles.footerAbout}`}>{t("landing.footerAbout")}</p>
        <div className={styles.footerLinks}>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            {t("landing.github")}
          </a>
          <a href={UPSTREAM_URL} target="_blank" rel="noreferrer">
            {t("landing.originalProject")}
          </a>
          <a href={LICENSE_URL} target="_blank" rel="noreferrer">
            {t("landing.license")}
          </a>
          <Link to="/terms">{t("legal.termsTitle")}</Link>
          <Link to="/privacy">{t("legal.privacyTitle")}</Link>
          <a href={`mailto:${CONTACT_EMAIL}`}>{t("landing.contact")}</a>
          <SupportLink />
        </div>
        <p className={`sf-muted ${styles.footerAbout}`}>{t("support.summary")}</p>
        <p className={`sf-muted ${styles.copyright}`}>
          {t("landing.footer", { year: new Date().getFullYear() })}
        </p>
      </footer>
    </div>
  );
}
