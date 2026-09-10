import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { TestSuitePage } from "@/components/dashboard/test-suite-page";

type DashboardProjectsTestSuitePageProps = {
  searchParams?:
    | {
        projectName?: string;
      }
    | Promise<{
        projectName?: string;
      }>;
};

export default async function DashboardProjectsTestSuitePage({
  searchParams
}: DashboardProjectsTestSuitePageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const projectName =
    resolvedSearchParams?.projectName?.trim() || "New evaluation project";

  return (
    <DashboardShell activeSection="projects">
      <TestSuitePage projectName={projectName} />
    </DashboardShell>
  );
}
