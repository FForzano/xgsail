import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import it from "./locales/it.json";

// Browser language with an English fallback; persisted choice via localStorage.
const stored = localStorage.getItem("sf-lang");
const browserLang = navigator.language?.slice(0, 2);

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    it: { translation: it },
  },
  lng: stored ?? (browserLang === "it" ? "it" : "en"),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: "en" | "it") {
  localStorage.setItem("sf-lang", lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
