import { useLanguage, useTranslation } from "@/i18n";

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** A `YYYY-MM-DD` day as people say it: today, yesterday, else a short date in the chosen language. Noon keeps a day
    from slipping to the one before west of UTC. */
export function useDayName(): (day: string) => string {
  const { t } = useTranslation();
  const { language } = useLanguage();
  return (day) => {
    const diff = Math.round((Date.parse(today()) - Date.parse(day)) / 864e5);
    if (diff === 0) return t("home.today");
    if (diff === 1) return t("home.yesterday");
    return new Date(`${day}T12:00:00`).toLocaleDateString(language, { month: "short", day: "numeric" });
  };
}
