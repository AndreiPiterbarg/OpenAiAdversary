import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { Book, Database, FileBox, FolderDot, Mail } from "lucide-react";

import { cn } from "@/lib/utils";
import logo from "@/assets/logo.svg";

type DashboardSection = "projects" | "models" | "datasets";

type DashboardShellProps = {
  activeSection: DashboardSection;
  children: ReactNode;
};

const primaryNav = [
  {
    key: "projects",
    label: "Projects",
    href: "/dashboard/projects",
    icon: FolderDot,
  },
  {
    key: "models",
    label: "Models",
    href: "/dashboard/models",
    icon: FileBox,
  },
  {
    key: "datasets",
    label: "Datasets",
    href: "/dashboard/datasets",
    icon: Database,
  },
] as const;

const secondaryNav = [
  {
    label: "Documentation",
    href: "#",
    icon: Book,
  },
  {
    label: "Support",
    href: "#",
    icon: Mail,
  },
] as const;

export function DashboardShell({
  activeSection,
  children,
}: DashboardShellProps) {
  return (
    <main className="min-h-screen bg-[#111111] px-4 pb-6 pt-12 text-[#eeeeee] md:px-8 md:pb-12 md:pt-12">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-16">
        <header className="flex items-center justify-between">
          <Link
            href="/dashboard/projects"
            aria-label="Go to dashboard projects"
            className="motion-interactive inline-flex h-10 w-10 items-center justify-center rounded-[8px]"
          >
            <Image
              src={logo}
              alt="Mistral logo"
              priority
              className="h-[30px] w-auto dashboard-logo-filter"
            />
          </Link>

          <div className="flex items-center gap-4 text-sm">
            <button
              type="button"
              className="motion-link font-medium text-[#eeeeee] transition-opacity hover:opacity-80"
            >
              Settings
            </button>
            <div className="motion-interactive flex h-8 w-8 items-center justify-center rounded-[8px] bg-[#222222] text-xs font-medium text-[#eeeeee]">
              AP
            </div>
          </div>
        </header>
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:gap-16">
          <aside className="md:min-h-[740px] md:w-[156px] md:flex-shrink-0 md:justify-between">
            <div className="flex flex-col gap-6 md:h-full md:justify-between">
              <nav className="grid grid-cols-3 gap-[2px] md:flex md:flex-col md:gap-[2px]">
                {primaryNav.map(({ key, label, href, icon: Icon }) => {
                  const active = key === activeSection;
                  return (
                    <Link
                      key={key}
                      href={href}
                      className={cn(
                        "motion-interactive hover:translate-y-0 inline-flex items-center gap-2 rounded-[8px] px-2 py-2 text-sm transition-colors",
                        active
                          ? "bg-[#1a1a1a] text-[#eeeeee]"
                          : "text-[#aaaaaa] hover:bg-[#1a1a1a] hover:text-[#eeeeee]",
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span>{label}</span>
                    </Link>
                  );
                })}
              </nav>

              <nav className="hidden flex-col gap-[2px] md:flex">
                {secondaryNav.map(({ label, href, icon: Icon }) => (
                  <Link
                    key={label}
                    href={href}
                    className="motion-interactive hover:translate-y-0 inline-flex items-center gap-2 rounded-[8px] px-2 py-2 text-sm text-[#aaaaaa] transition-colors hover:bg-[#1a1a1a] hover:text-[#eeeeee]"
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{label}</span>
                  </Link>
                ))}
              </nav>
            </div>
          </aside>

          <section className="w-full max-w-[936px]">{children}</section>
        </div>
      </div>
    </main>
  );
}
