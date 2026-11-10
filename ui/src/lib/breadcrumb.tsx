import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

export type Crumb = { label: string; to?: "/reports" | "/memory" };
export type PageHeading = { title: string; crumbs: Crumb[]; source?: string };

const APP_NAME = "Whaat?!";

const DEFAULT_HEADING: PageHeading = { title: APP_NAME, crumbs: [] };

/** A page with no title of its own, such as a list, is named after the app and the section. */
export function sectionTitle(section: string): string {
  return `${APP_NAME} – ${section}`;
}

type HeadingState = { heading: PageHeading; setHeading: (heading: PageHeading | null) => void };

const HeadingContext = createContext<HeadingState>({ heading: DEFAULT_HEADING, setHeading: () => {} });

export function PageHeadingProvider({ children }: { children: ReactNode }) {
  const [heading, setHeading] = useState<PageHeading | null>(null);
  return <HeadingContext value={{ heading: heading ?? DEFAULT_HEADING, setHeading }}>{children}</HeadingContext>;
}

/** A page names itself for the shared header and footer: its title, the crumbs after the app's name, its source. */
export function usePageHeading(title: string, crumbs: Crumb[] = [], source?: string): void {
  const { setHeading } = useContext(HeadingContext);
  const trail = JSON.stringify(crumbs);
  useEffect(() => {
    setHeading({ title, crumbs: JSON.parse(trail) as Crumb[], source });
    return () => setHeading(null);
  }, [title, trail, source, setHeading]);
}

export function useCurrentHeading(): PageHeading {
  return useContext(HeadingContext).heading;
}
