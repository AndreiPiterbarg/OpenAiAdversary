import { LoadingLabPage } from "@/components/dashboard/loading-lab-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function DashboardLoadingLabRoute() {
  return (
    <DashboardShell activeSection="projects">
      <LoadingLabPage />
    </DashboardShell>
  );
}
