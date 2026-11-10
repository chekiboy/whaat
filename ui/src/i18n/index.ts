import i18n from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";
import { updatePreferences } from "@/client";
import { en } from "./en";
import { hu } from "./hu";

export const LANGUAGES = ["en", "hu"] as const;
export type Language = (typeof LANGUAGES)[number];
const KEY = "whaat-lang";

declare module "i18next" {
  interface CustomTypeOptions {
    resources: { translation: typeof en };
  }
}

function stored(): Language {
  try {
    const value = localStorage.getItem(KEY);
    return (LANGUAGES as readonly string[]).includes(value ?? "") ? (value as Language) : "en";
  } catch {
    return "en";
  }
}

/** The language the server's preferences name, with
    the browser's copy shown until they load; English unless the user switched; the choice is kept per browser. */
export function setupI18n(): typeof i18n {
  const lng = stored();
  document.documentElement.lang = lng;
  void i18n.use(initReactI18next).init({
    resources: { en: { translation: en }, hu: { translation: hu } },
    lng,
    fallbackLng: "en",
    interpolation: { escapeValue: false },
    initAsync: false,
  });
  return i18n;
}

/** Show a language without saving it: the one the server's preferences name, when they load. */
export function applyLanguage(next: Language): void {
  if (i18n.language === next) return;
  void i18n.changeLanguage(next);
  document.documentElement.lang = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* the browser copy only saves a flash of the other language on load */
  }
}

export function useLanguage(): { language: Language; setLanguage: (language: Language) => void } {
  const { i18n: instance } = useTranslation();
  const language = (
    (LANGUAGES as readonly string[]).includes(instance.language) ? instance.language : "en"
  ) as Language;
  const setLanguage = (next: Language) => {
    applyLanguage(next);
    void updatePreferences({ body: { language: next } });
  };
  return { language, setLanguage };
}

export type { TFunction } from "i18next";
export { useTranslation };
