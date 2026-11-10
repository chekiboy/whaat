import { createFileRoute } from "@tanstack/react-router";
import { ModuleBar, ModuleBarSection } from "@/components/shell/module-bar";
import { useTranslation } from "@/i18n";
import { sectionTitle, usePageHeading } from "@/lib/breadcrumb";
import { ROADMAP, SPOTLIGHT, TODAY } from "@/lib/home-content";
import "@/styles/overview.css";

export const Route = createFileRoute("/about")({
  component: About,
});

const STATUS_COLOUR: Record<string, string> = {
  done: "var(--stripe-teal)",
  now: "var(--stripe-orange)",
  next: "var(--stripe-blue)",
  later: "#8a7f6c",
};
const SECTIONS = [
  ["ab-spot", "spot"],
  ["ab-today", "today"],
  ["ab-road", "road"],
] as const;

/* What Whaat?! is. */
function About() {
  const { t } = useTranslation();
  usePageHeading(sectionTitle("About"), [{ label: t("about.title") }]);
  return (
    <div className="sh-view ab">
      <ModuleBar>
        <ModuleBarSection title={t("about.title")}>
          {[
            ["ab-top", "Whaat?!"] as const,
            ...SECTIONS.map(([id, key]) => [id, t(`about.sections.${key}`)] as const),
          ].map(([id, label]) => (
            <button
              type="button"
              key={id}
              className="sh-item"
              onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            >
              {label}
            </button>
          ))}
        </ModuleBarSection>
      </ModuleBar>
      <div className="sh-tb">
        <h1>{t("about.title")}</h1>
        <span className="meta">{t("about.tagline")}</span>
      </div>
      <div className="sh-pane">
        <h2 className="ab-h" id="ab-top">
          Whaat?!
        </h2>
        <p className="ab-lead">{t("about.lead1")}</p>
        <p className="ab-lead">{t("about.lead2")}</p>
        <h2 className="ab-h" id="ab-spot">
          {t("about.sections.spot")}
        </h2>
        <div className="ab-spot">
          {SPOTLIGHT.map((key) => (
            <article key={key}>
              <div className="k">{t(`about.spotlight.${key}.kicker`)}</div>
              <h4>{t(`about.spotlight.${key}.title`)}</h4>
              <p>{t(`about.spotlight.${key}.text1`)}</p>
              <p>{t(`about.spotlight.${key}.text2`)}</p>
              <p className="w">{t(`about.spotlight.${key}.where`)}</p>
            </article>
          ))}
        </div>
        <h2 className="ab-h" id="ab-today">
          {t("about.sections.today")}
        </h2>
        <div className="ab-feats">
          {TODAY.map(([key, stripe]) => (
            <article key={key} style={{ borderLeftColor: stripe }}>
              <h4>{t(`about.today.${key}.title`)}</h4>
              <p>{t(`about.today.${key}.text`)}</p>
            </article>
          ))}
        </div>
        <h2 className="ab-h" id="ab-road">
          {t("about.sections.road")}
        </h2>
        <div className="ab-road">
          {ROADMAP.map(([key, status]) => (
            <article key={key} className={status} style={{ "--c": STATUS_COLOUR[status] } as React.CSSProperties}>
              <span className="s">{t(`about.status.${status}`)}</span>
              <div>
                <h4>{t(`about.roadmap.${key}.title`)}</h4>
                <p>{t(`about.roadmap.${key}.text`)}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
