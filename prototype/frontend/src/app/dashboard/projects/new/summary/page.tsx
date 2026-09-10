import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { SummaryPage } from "@/components/dashboard/summary-page";

type DashboardProjectsSummaryPageProps = {
  searchParams?:
    | {
        projectName?: string;
      }
    | Promise<{
        projectName?: string;
      }>;
};

export default async function DashboardProjectsSummaryPage({
  searchParams
}: DashboardProjectsSummaryPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const projectName =
    resolvedSearchParams?.projectName?.trim() || "New evaluation project";

  return (
    <DashboardShell activeSection="projects">
      <SummaryPage projectName={projectName} />
    </DashboardShell>
  );
}
