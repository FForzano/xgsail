export const BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/xgsail";
export const GITHUB_URL = "https://github.com/FForzano/xgsail";
export const LICENSE_URL = `${GITHUB_URL}/blob/main/LICENSE`;
export const UPSTREAM_URL = "https://github.com/sailframes/core";
export const E1_REPO_URL = "https://github.com/FForzano/xgsail-e1";
export const CONTACT_EMAIL = "f.forzano@ieee.org";
export const DEVELOPER_GITHUB_URL = "https://github.com/FForzano";
// Signed release APK attached to every vX.Y.Z GitHub Release by
// .github/workflows/android-release.yml — sideloading path while the app
// isn't published to the Play Store (see README "Native apps"). The
// workflow renames Gradle's default app-release.apk to XGSail.apk before
// upload, so this filename must stay in sync with that rename step.
export const ANDROID_APK_URL = `${GITHUB_URL}/releases/latest/download/XGSail.apk`;
