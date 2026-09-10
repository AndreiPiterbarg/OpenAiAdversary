"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronRight } from "lucide-react";

import { WizardBackButton } from "@/components/dashboard/wizard-back-button";

type SuiteCard = {
  id: string;
  title: string;
  items: string[];
  selected?: boolean;
};

const topRowCards: SuiteCard[] = [
  {
    id: "environmental-robustness",
    title: "Environmental stress",
    items: ["Fog", "Rain", "Low light", "Hard shadows"]
  },
  {
    id: "sensor-degradation",
    title: "Sensor degradation",
    items: ["Motion blur", "Image noise", "Resolution loss", "Compression artifacts"],
    selected: true
  },
  {
    id: "semantic-manipulation",
    title: "Semantic edits",
    items: ["Inpainting", "Object removal", "Camouflage", "Distractor insertion"]
  }
];

const bottomRowCards: SuiteCard[] = [
  {
    id: "document-degradation",
    title: "Document corruption",
    items: ["Layout shift (column bleed)", "Overlays (watermarks, stamps)"],
    selected: true
  }
];

type TestSuitePageProps = {
  projectName: string;
};

function SuiteCardItem({
  id,
  title,
  items,
  selected,
  onToggle
}: SuiteCard & { onToggle: () => void }) {
  return (
    <button
      type="button"
      id={id}
      onClick={onToggle}
      className={`motion-interactive flex h-[245px] w-full flex-col items-start justify-start overflow-hidden rounded-[8px] border border-[#222222] px-6 py-5 text-left ${
        selected ? "bg-[#1a1a1a]" : "bg-transparent"
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-semibold leading-5 text-[#eeeeee]">
        {selected ? <Check className="h-4 w-4" /> : null}
        <h2>{title}</h2>
      </div>

      <ul className="mt-2 space-y-2 text-sm leading-5 text-[#aaaaaa]">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </button>
  );
}

export function TestSuitePage({ projectName }: TestSuitePageProps) {
  const router = useRouter();
  const initialSelected = [...topRowCards, ...bottomRowCards]
    .filter((card) => card.selected)
    .map((card) => card.id);
  const [activeCardIds, setActiveCardIds] = useState<Set<string>>(
    () => new Set(initialSelected)
  );

  const toggleCard = (cardId: string) => {
    setActiveCardIds((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  };

  return (
    <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
      <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4 pr-6">
        <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Projects</p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="truncate text-2xl font-light leading-7 text-[#aaaaaa]">{projectName}</p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="text-2xl font-light leading-7 text-[#eeeeee]">Select test suite</p>
      </div>

      <div className="motion-page-enter motion-delay-2 flex w-full flex-wrap items-start gap-6">
        {topRowCards.map((card) => (
          <div key={card.id} className="w-full md:w-[calc(50%-12px)] xl:w-[296px]">
            <SuiteCardItem
              {...card}
              selected={activeCardIds.has(card.id)}
              onToggle={() => toggleCard(card.id)}
            />
          </div>
        ))}
      </div>

      <div className="motion-page-enter motion-delay-3 flex w-full flex-wrap items-start gap-y-6">
        {bottomRowCards.map((card) => (
          <div key={card.id} className="w-full md:w-[calc(50%-12px)] xl:w-[296px]">
            <SuiteCardItem
              {...card}
              selected={activeCardIds.has(card.id)}
              onToggle={() => toggleCard(card.id)}
            />
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between gap-3">
        <WizardBackButton
          onClick={() =>
            router.push(
              `/dashboard/projects/new?projectName=${encodeURIComponent(projectName)}`
            )
          }
        />
        <button
          type="button"
          onClick={() =>
            router.push(
              `/dashboard/projects/new/summary?projectName=${encodeURIComponent(
                projectName.trim() || "New evaluation project"
              )}`
            )
          }
          className="motion-interactive inline-flex min-h-9 items-center justify-center rounded-[8px] bg-[#fafafa] px-4 py-2 text-sm font-medium text-[#171717] transition-opacity hover:opacity-90"
        >
          Continue to summary
        </button>
      </div>
    </div>
  );
}
