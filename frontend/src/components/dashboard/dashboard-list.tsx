import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { ChevronRight, Plus } from "lucide-react";

import { cn } from "@/lib/utils";
import logo from "@/assets/logo.svg";

type TagTone = "yellow" | "cyan" | "green";

type ItemTag = {
  label: string;
  tone: TagTone;
};

type DashboardItem = {
  id?: string;
  title: string;
  subtitle: string;
  tag?: ItemTag;
  leadingGhostLogo?: boolean;
};

type DashboardListPageProps = {
  title: string;
  topRight?: ReactNode;
  ctaTitle: string;
  ctaSubtitle: string;
  ctaHref?: string;
  items: DashboardItem[];
};

const tagToneClasses: Record<TagTone, string> = {
  yellow: "bg-[rgba(255,146,48,0.4)] text-[#ffd600]",
  cyan: "bg-[rgba(0,136,255,0.4)] text-[#00ffff]",
  green: "bg-[rgba(52,199,89,0.4)] text-[#2aff7c]"
};

export function DashboardListPage({
  title,
  topRight,
  ctaTitle,
  ctaSubtitle,
  ctaHref,
  items
}: DashboardListPageProps) {
  const ctaContent = (
    <>
      <div className="flex h-8 w-8 items-center justify-center rounded-[8px] bg-[#222222]">
        <Plus className="h-4 w-4 text-[#eeeeee]" />
      </div>
      <div className="flex flex-col gap-0.5">
        <p className="text-sm text-[#eeeeee]">{ctaTitle}</p>
        <p className="text-sm text-[#aaaaaa]">{ctaSubtitle}</p>
      </div>
    </>
  );

  return (
    <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
      <div className="motion-page-enter motion-delay-2 flex min-h-8 items-center justify-between gap-4">
        <h1 className="text-2xl font-light text-[#eeeeee]">{title}</h1>
        {topRight}
      </div>

      {ctaHref ? (
        <Link
          href={ctaHref}
          className="motion-interactive motion-page-enter motion-delay-2 flex w-full items-center gap-6 rounded-[8px] border-2 border-dashed border-[#222222] p-6 text-left transition-colors hover:border-[#333333]"
        >
          {ctaContent}
        </Link>
      ) : (
        <button
          type="button"
          className="motion-interactive motion-page-enter motion-delay-2 flex w-full items-center gap-6 rounded-[8px] border-2 border-dashed border-[#222222] p-6 text-left transition-colors hover:border-[#333333]"
        >
          {ctaContent}
        </button>
      )}

      {items.map((item, index) => (
        <button
          type="button"
          key={item.id ?? `${item.title}-${item.subtitle}-${index}`}
          style={{ animationDelay: `${160 + index * 30}ms` }}
          className="motion-interactive motion-page-enter flex w-full items-center gap-6 rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6 text-left transition-colors hover:border-[#333333]"
        >
          <div className="flex min-w-0 flex-1 items-center justify-between gap-6">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-[7px]">
                {item.leadingGhostLogo ? (
                  <Image
                    src={logo}
                    alt=""
                    aria-hidden
                    width={12}
                    height={16}
                    className="dashboard-logo-filter h-4 w-[12px] shrink-0"
                  />
                ) : null}
                <p className="truncate text-sm text-[#eeeeee]">{item.title}</p>
              </div>
              <p className="truncate text-sm text-[#aaaaaa]">{item.subtitle}</p>
            </div>
            {item.tag ? (
              <span
                className={cn(
                  "inline-flex shrink-0 items-center rounded-[8px] px-2 py-1 text-sm",
                  tagToneClasses[item.tag.tone]
                )}
              >
                {item.tag.label}
              </span>
            ) : null}
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-[#aaaaaa]" />
        </button>
      ))}
    </div>
  );
}
