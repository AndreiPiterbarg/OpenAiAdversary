import { NewProjectPage } from "@/components/dashboard/new-project-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

type DashboardProjectsNewPageProps = {
  searchParams?:
    | {
        projectName?: string;
      }
    | Promise<{
        projectName?: string;
      }>;
};

export default async function DashboardProjectsNewPage({
  searchParams
}: DashboardProjectsNewPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const projectName = resolvedSearchParams?.projectName?.trim();

  return (
    <DashboardShell activeSection="projects">
      <NewProjectPage initialProjectName={projectName} />
    </DashboardShell>
  );
}
