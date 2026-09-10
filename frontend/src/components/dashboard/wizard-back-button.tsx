"use client";

import { type ComponentProps } from "react";

import { cn } from "@/lib/utils";

type WizardBackButtonProps = ComponentProps<"button">;

export function WizardBackButton({ className, ...props }: WizardBackButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "wizard-back-button inline-flex min-h-9 items-center justify-center rounded-[8px] border-2 border-[#222222] px-4 py-2 text-sm font-normal leading-5 text-[#aaaaaa]",
        className
      )}
      {...props}
    >
      Back
    </button>
  );
}
