/** Stylized illustration for the "self-hosted" landing card — the one feature with no corresponding app screen to show. */
export function SelfHostedArt() {
  return (
    <svg viewBox="0 0 100 100" className="sf-landing__art">
      <rect x="1" y="1" width="98" height="98" rx="8" className="sf-landing__art-bg" />
      <rect x="24" y="26" width="52" height="14" rx="3" className="sf-landing__art-bar" />
      <rect x="24" y="43" width="52" height="14" rx="3" className="sf-landing__art-bar" />
      <rect x="24" y="60" width="52" height="14" rx="3" className="sf-landing__art-bar" />
      <circle cx="32" cy="33" r="2" className="sf-landing__art-dot" />
      <circle cx="32" cy="50" r="2" className="sf-landing__art-dot" />
      <circle cx="32" cy="67" r="2" className="sf-landing__art-dot" />
    </svg>
  );
}
