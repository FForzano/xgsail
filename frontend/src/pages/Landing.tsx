import { Navigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { isNativeApp } from "@/config/platform";
import { SelfHostedArt } from "@/components/landing/FeatureArt";

const GITHUB_URL = "https://github.com/FForzano/xgsail";
const LICENSE_URL = `${GITHUB_URL}/blob/main/LICENSE`;
const UPSTREAM_URL = "https://github.com/sailframes/core";
const CONTACT_EMAIL = "f.forzano@ieee.org";

// Real product screenshots for features 1-5 — feature 6 (self-hosted) has no
// single app screen to show, so it keeps a stylized illustration instead.
const FEATURE_SHOTS: Record<number, string> = {
  1: "/landing/playback.png",
  2: "/landing/analysis.png",
  3: "/landing/race.png",
  4: "/landing/clubs.png",
  5: "/landing/devices.png",
};
const FEATURE_KEYS = [1, 2, 3, 4, 5, 6] as const;

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
  if (status === "authed") return <Navigate to="/diario/activities" replace />;
  if (isNativeApp) return <Navigate to="/login" replace />;

  return (
    <div className="sf-landing">
      <header className="sf-landing__nav">
        <Link to="/" className="sf-navbar__brand">
          <img src="/logo.svg" alt="" className="sf-navbar__logo" />
          <span className="sf-landing__brand-text">
            <span>XGSail</span>
            <span className="sf-landing__brand-tagline">{t("common.tagline")}</span>
          </span>
        </Link>
        <div className="sf-landing__nav-actions">
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

      <main className="sf-landing__hero">
        <p className="sf-landing__eyebrow">{t("common.tagline")}</p>
        <h1 className="sf-landing__title">{t("landing.heroTitle")}</h1>
        <p className="sf-landing__tagline">{t("landing.heroSubtitle")}</p>
        <div className="sf-landing__cta">
          <Link to="/register">
            <Button>{t("landing.getStarted")}</Button>
          </Link>
          <Link to="/login">
            <Button variant="ghost">{t("auth.login")}</Button>
          </Link>
        </div>
      </main>

      <section className="sf-landing__section">
        <h2 className="sf-landing__section-title">{t("landing.insightsTitle")}</h2>
        <div className="sf-landing__features">
          {FEATURE_KEYS.map((n) => (
            <div className="sf-card" key={n}>
              {FEATURE_SHOTS[n] ? (
                <img src={FEATURE_SHOTS[n]} alt="" className="sf-landing__shot" />
              ) : (
                <SelfHostedArt />
              )}
              <h3 className="sf-card__title">{t(`landing.feature${n}Title`)}</h3>
              <p className="sf-muted">{t(`landing.feature${n}Body`)}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="sf-landing__footer">
        <p className="sf-muted sf-landing__footer-about">{t("landing.footerAbout")}</p>
        <div className="sf-landing__footer-links">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            {t("landing.github")}
          </a>
          <a href={UPSTREAM_URL} target="_blank" rel="noreferrer">
            {t("landing.originalProject")}
          </a>
          <a href={LICENSE_URL} target="_blank" rel="noreferrer">
            {t("landing.license")}
          </a>
          <a href={`mailto:${CONTACT_EMAIL}`}>{t("landing.contact")}</a>
        </div>
        <p className="sf-muted sf-landing__copyright">
          {t("landing.footer", { year: new Date().getFullYear() })}
        </p>
      </footer>
    </div>
  );
}
