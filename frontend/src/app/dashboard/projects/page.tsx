import Link from "next/link";
import { Play } from "lucide-react";
import { DashboardListPage } from "@/components/dashboard/dashboard-list";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

const projects = [
  {
    id: "project-1",
    title: "Warehouse Safety Baseline",
    subtitle: "Last run 2 hours ago",
    tag: { label: "Baseline", tone: "yellow" as const }
  },
  {
    id: "project-2",
    title: "Voxtral Night Shift Audit",
    subtitle: "18 scenarios flagged for review",
    tag: { label: "Fine-tuning", tone: "cyan" as const }
  },
  {
    id: "project-3",
    title: "Retail Shelf Occlusion Study",
    subtitle: "Evaluation complete",
    tag: { label: "Completed", tone: "green" as const }
  },
  {
    id: "project-4",
    title: "Autonomous Forklift Validation",
    subtitle: "Scheduled to run tonight",
    tag: { label: "Queued", tone: "yellow" as const }
  },
  {
    id: "project-5",
    title: "Perimeter Camera Stress Test",
    subtitle: "Model update in progress",
    tag: { label: "Fine-tuning", tone: "cyan" as const }
  }
];

export default function DashboardProjectsPage() {
  return (
    <DashboardShell activeSection="projects">
      <DashboardListPage
        title="Projects"
        topRight={
          <Link href="/demo" className="motion-interactive inline-flex items-center gap-2 rounded-[8px] border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2 text-sm text-[#eeeeee] hover:border-[#333333]">
            <Play className="h-3.5 w-3.5" aria-hidden="true" /> Watch demo
          </Link>
        }
        ctaTitle="Create evaluation project"
        ctaSubtitle="Define your model, dataset, and attack plan"
        ctaHref="/dashboard/projects/new"
        items={projects}
      />
    </DashboardShell>
  );
}
