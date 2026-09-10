"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";

import logo from "@/assets/logo.svg";
import { ProcessingLoader } from "@/components/dashboard/processing-loader";
import { WizardBackButton } from "@/components/dashboard/wizard-back-button";

type FineTuningSummaryPageProps = {
  projectName: string;
};

type RankedAttack = {
  label: string;
  value: string;
};

type ModelBlock = {
  stats: {
    accuracy_clean: number;
    latency_clean: number;
    accuracy_edited: number;
    latency_edited: number;
  };
  attack_ranking: RankedAttack[];
};

type ComparisonFrontendData = {
  comparison: boolean;
  original: ModelBlock;
  finetuned: ModelBlock;
};

type ComparisonRow = {
  attack: string;
  original: string;
  fineTuned: string;
};

type MetricCard = {
  title: "Original" | "Fine-tuned";
  subtitle: string;
  value: string;
  fineTuned?: boolean;
};

function buildMetricCards(data: ComparisonFrontendData): {
  withoutAttacks: MetricCard[];
  withAttacks: MetricCard[];
  comparisonRows: ComparisonRow[];
} {
  const withoutAttacks: MetricCard[] = [
    { title: "Original", subtitle: "Overall Accuracy", value: `${Math.round(data.original.stats.accuracy_clean)}` },
    { title: "Original", subtitle: "Response latency", value: `${Math.round(data.original.stats.latency_clean)}` },
    { title: "Fine-tuned", subtitle: "Overall Accuracy", value: `${Math.round(data.finetuned.stats.accuracy_clean)}`, fineTuned: true },
    { title: "Fine-tuned", subtitle: "Response latency", value: `${Math.round(data.finetuned.stats.latency_clean)}`, fineTuned: true },
  ];

  const withAttacks: MetricCard[] = [
    { title: "Original", subtitle: "Degradation rate", value: `${Math.round(100 - data.original.stats.accuracy_edited)}` },
    { title: "Original", subtitle: "Response latency", value: `${Math.round(data.original.stats.latency_edited)}` },
    { title: "Fine-tuned", subtitle: "Degradation rate", value: `${Math.round(100 - data.finetuned.stats.accuracy_edited)}`, fineTuned: true },
    { title: "Fine-tuned", subtitle: "Response latency", value: `${Math.round(data.finetuned.stats.latency_edited)}`, fineTuned: true },
  ];

  // Build comparison rows by matching attack labels across original and finetuned rankings
  const ftMap = new Map(data.finetuned.attack_ranking.map((r) => [r.label, r.value]));
  const comparisonRows: ComparisonRow[] = data.original.attack_ranking
    .filter((r) => r.value !== "0%")
    .map((r) => ({
      attack: r.label,
      original: r.value,
      fineTuned: ftMap.get(r.label) ?? "0%",
    }));

  return { withoutAttacks, withAttacks, comparisonRows };
}

const fineTuningLoadingPhases = [
  {
    title: "Fine-tuning your model!",
    subtitle:
      "Adapting weights from the failed scenarios to improve robustness against adversarial attacks."
  },
  {
    title: "Validating improvements",
    subtitle:
      "Running evaluation passes to compare the original model against the fine-tuned model."
  },
  {
    title: "Finalizing fine-tuning summary",
    subtitle:
      "Preparing effectiveness comparison metrics and latency impact for this run."
  }
];

function MetricGrid({ cards }: { cards: MetricCard[] }) {
  return (
    <div className="grid w-full gap-6 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card, index) => (
        <article
          key={`${card.title}-${card.subtitle}-${index}`}
          style={{ animationDelay: `${140 + index * 30}ms` }}
          className="motion-interactive motion-page-enter flex items-start justify-between rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6"
        >
          <div>
            <div className="flex items-center gap-[7px] text-sm font-semibold leading-5 text-[#eeeeee]">
              {card.fineTuned ? (
                <Image
                  src={logo}
                  alt=""
                  aria-hidden
                  width={12}
                  height={16}
                  className="dashboard-logo-filter h-4 w-[12px]"
                />
              ) : null}
              <p>{card.title}</p>
            </div>
            <p className="text-sm leading-5 text-[#aaaaaa]">{card.subtitle}</p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-[2px] bg-[#222222] text-2xl font-light leading-6 text-[#eeeeee]">
            {card.value}
          </div>
        </article>
      ))}
    </div>
  );
}

export function FineTuningSummaryPage({ projectName }: FineTuningSummaryPageProps) {
  const router = useRouter();
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [data, setData] = useState<ComparisonFrontendData | null>(null);

  useEffect(() => {
    fetch("/data/comparison_frontend_data.json")
      .then((res) => res.json())
      .then((json: ComparisonFrontendData) => setData(json))
      .catch(() => {});
  }, []);

  const handleLoadingComplete = useCallback(() => {
    setIsLoadingSummary(false);
  }, []);

  const { withoutAttacks, withAttacks, comparisonRows } = data
    ? buildMetricCards(data)
    : { withoutAttacks: [], withAttacks: [], comparisonRows: [] };

  if (isLoadingSummary) {
    return (
      <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
        <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4">
          <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Projects</p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="truncate text-2xl font-light leading-7 text-[#aaaaaa]">
            {projectName}
          </p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="text-2xl font-light leading-7 text-[#eeeeee]">
            Fine-tuning summary
          </p>
        </div>

        <ProcessingLoader
          phases={fineTuningLoadingPhases}
          durationMs={5600}
          onComplete={handleLoadingComplete}
        />
      </div>
    );
  }

  return (
    <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
      <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4">
        <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Projects</p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="truncate text-2xl font-light leading-7 text-[#aaaaaa]">
          {projectName}
        </p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="text-2xl font-light leading-7 text-[#eeeeee]">
          Fine-tuning summary
        </p>
      </div>

      <div className="motion-page-enter motion-delay-2 flex flex-col gap-3">
        <h2 className="text-sm font-semibold leading-5 text-[#eeeeee]">
          Without attacks
        </h2>
        <MetricGrid cards={withoutAttacks} />
      </div>

      <div className="motion-page-enter motion-delay-2 flex flex-col gap-3">
        <h2 className="text-sm font-semibold leading-5 text-[#eeeeee]">
          With attacks
        </h2>
        <MetricGrid cards={withAttacks} />
      </div>

      <div className="motion-page-enter motion-delay-3 flex flex-col gap-3">
        <h2 className="text-sm font-semibold leading-5 text-[#eeeeee]">
          Effectiveness comparison
        </h2>

        <section className="rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
          <div className="space-y-2 text-sm leading-5">
            <div className="grid grid-cols-3 gap-4 font-semibold text-[#eeeeee]">
              <p>Attacks</p>
              <p className="text-right">Original</p>
              <p className="text-right">Fine-tuned</p>
            </div>
            {comparisonRows.map((row) => (
              <div
                key={row.attack}
                className="grid grid-cols-3 gap-4 text-sm leading-5 text-[#aaaaaa]"
              >
                <p>{row.attack}</p>
                <p className="text-right">{row.original}</p>
                <p className="text-right">{row.fineTuned}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="flex items-center justify-between gap-3">
        <WizardBackButton
          onClick={() =>
            router.push(
              `/dashboard/projects/new/summary?projectName=${encodeURIComponent(
                projectName.trim() || "New evaluation project"
              )}`
            )
          }
        />
        <button
          type="button"
          onClick={() => router.push("/dashboard/models?tab=fine-tuned")}
          className="motion-interactive inline-flex min-h-9 items-center justify-center rounded-[8px] bg-[#fafafa] px-4 py-2 text-sm font-medium text-[#171717] transition-opacity hover:opacity-90"
        >
          Use fine-tuned model
        </button>
      </div>
    </div>
  );
}
