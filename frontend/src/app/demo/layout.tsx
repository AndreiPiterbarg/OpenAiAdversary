import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export const metadata: Metadata = {
  title: "Live monitor · Adversary",
  description: "Monitor an adversarial evaluation, from repository history to a paired failure.",
};

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell activeSection="projects">{children}</DashboardShell>;
}
