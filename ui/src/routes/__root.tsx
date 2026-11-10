import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import { AppShell } from "@/components/shell/app-shell";
import { PageHeadingProvider } from "@/lib/breadcrumb";
import { PersonaProvider } from "@/lib/persona";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  notFoundComponent: () => <p className="font-mono text-muted-foreground">Nothing here.</p>,
});

function RootLayout() {
  return (
    <PersonaProvider>
      <PageHeadingProvider>
        <AppShell>
          <Outlet />
        </AppShell>
      </PageHeadingProvider>
    </PersonaProvider>
  );
}
