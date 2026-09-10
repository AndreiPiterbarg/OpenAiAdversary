import { FineTuningSummaryPage } from "@/components/dashboard/fine-tuning-summary-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

type DashboardProjectsFineTuningPageProps = {
  searchParams?:
    | {
        projectName?: string;
      }
    | Promise<{
        projectName?: string;
      }>;
};

export default async function DashboardProjectsFineTuningPage({
  searchParams
}: DashboardProjectsFineTuningPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const projectName =
    resolvedSearchParams?.projectName?.trim() || "New evaluation project";

  return (
    <DashboardShell activeSection="projects">
      <FineTuningSummaryPage projectName={projectName} />
    </DashboardShell>
  );
}
