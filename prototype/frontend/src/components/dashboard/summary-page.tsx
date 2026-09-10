"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { ArrowLeft, ArrowRight, ChevronRight } from "lucide-react";

import logo from "@/assets/logo.svg";
import { ProcessingLoader } from "@/components/dashboard/processing-loader";
import { WizardBackButton } from "@/components/dashboard/wizard-back-button";

type SummaryPageProps = {
  projectName: string;
};

type StatCard = {
  title: string;
  subtitle: string;
  value: string;
  attack?: boolean;
};

type RankedAttack = {
  label: string;
  value: string;
};

type FailedScenario = {
  id: string;
  image_url: string;
  attacks: string;
  question: string;
  correct_response: string;
  model_response: string;
};

type FrontendData = {
  stats: {
    base_accuracy: number;
    base_response_latency: number;
    attack_degradation_rate: number;
    attack_response_latency: number;
  };
  attack_ranking: RankedAttack[];
  failed_scenarios: FailedScenario[];
  passed_scenarios: FailedScenario[];
};

const defaultStatCards: StatCard[] = [
  { title: "Base", subtitle: "Accuracy", value: "--" },
  { title: "Base", subtitle: "Response latency", value: "--" },
  { title: "Attack", subtitle: "Degradation rate", value: "--", attack: true },
  { title: "Attack", subtitle: "Response latency", value: "--", attack: true },
];

function parseAttackValue(v: string): number {
  return parseFloat(v.replace("%", "")) || 0;
}

function buildStatCards(stats: FrontendData["stats"]): StatCard[] {
  return [
    { title: "Base", subtitle: "Accuracy", value: String(stats.base_accuracy) },
    { title: "Base", subtitle: "Response latency", value: String(stats.base_response_latency) },
    { title: "Attack", subtitle: "Degradation rate", value: String(stats.attack_degradation_rate), attack: true },
    { title: "Attack", subtitle: "Response latency", value: String(stats.attack_response_latency), attack: true },
  ];
}


const runSummaryLoadingPhases = [
  {
    title: "Spooking your model!",
    subtitle:
      "Approx. 25mins remaining in this run. Meanwhile you can create new projects, add new models or datasets to work with in the future."
  },
  {
    title: "Simulating adversarial attacks",
    subtitle:
      "Applying blur, noise, compression, and environment shifts to stress test model behavior."
  },
  {
    title: "Compiling run summary",
    subtitle: "Ranking weak spots and preparing scenario-level findings for review."
  }
];

export function SummaryPage({ projectName }: SummaryPageProps) {
  const router = useRouter();
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [statCards, setStatCards] = useState<StatCard[]>(defaultStatCards);
  const [rankedAttacks, setRankedAttacks] = useState<RankedAttack[]>([]);
  const [failedScenarios, setFailedScenarios] = useState<FailedScenario[]>([]);
  const [passedScenarios, setPassedScenarios] = useState<FailedScenario[]>([]);
  const [totalFailed, setTotalFailed] = useState(0);
  const [totalPassed, setTotalPassed] = useState(0);
  const [scenarioFilter, setScenarioFilter] = useState<"failed" | "passed">(
    "failed"
  );
  const [activeImageIndex, setActiveImageIndex] = useState<number | null>(null);
  const [responseExpanded, setResponseExpanded] = useState(false);
  const [invalidImageSources, setInvalidImageSources] = useState<Set<string>>(
    () => new Set()
  );

  useEffect(() => {
    fetch("/data/frontend_data.json")
      .then((res) => res.json())
      .then((data: FrontendData) => {
        setStatCards(buildStatCards(data.stats));
        setRankedAttacks(data.attack_ranking);
        setFailedScenarios(data.failed_scenarios?.slice(0, 20) ?? []);
        setPassedScenarios(
          (data.passed_scenarios ?? []).slice(0, 20).map((s) => ({
            ...s,
            model_response: s.correct_response,
          }))
        );
        setTotalFailed(data.failed_scenarios?.length ?? 0);
        setTotalPassed(data.passed_scenarios?.length ?? 0);
      })
      .catch(() => {
        // keep defaults on error
      });
  }, []);

  const sorted = [...rankedAttacks].sort(
    (a, b) => parseAttackValue(b.value) - parseAttackValue(a.value)
  );
  const strongestAttacks = sorted.slice(0, 5);
  const weakestAttacks = sorted.slice(-5).reverse();

  const failedScenarioImages = failedScenarios.map((s) => s.image_url);
  const passedScenarioImages = passedScenarios.map((s) => s.image_url);
  const displayedScenarios =
    scenarioFilter === "passed" ? passedScenarios : failedScenarios;
  const displayedScenarioImages =
    scenarioFilter === "passed" ? passedScenarioImages : failedScenarioImages;
  const totalForFilter =
    scenarioFilter === "passed" ? totalPassed : totalFailed;
  const remainingCount = totalForFilter - displayedScenarios.length;
  const isViewerOpen = activeImageIndex !== null;
  const currentImage =
    activeImageIndex !== null ? displayedScenarioImages[activeImageIndex] : null;
  const isCurrentImageInvalid = currentImage
    ? invalidImageSources.has(currentImage)
    : false;
  const currentScenario =
    activeImageIndex !== null
      ? displayedScenarios[activeImageIndex] ?? null
      : null;

  useEffect(() => {
    setActiveImageIndex(null);
    setResponseExpanded(false);
  }, [scenarioFilter]);

  useEffect(() => {
    setResponseExpanded(false);
  }, [activeImageIndex]);

  useEffect(() => {
    if (!isViewerOpen || displayedScenarioImages.length === 0) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveImageIndex(null);
        return;
      }

      if (event.key === "ArrowLeft") {
        setActiveImageIndex((prev) => {
          if (prev === null) return null;
          return (prev - 1 + displayedScenarioImages.length) % displayedScenarioImages.length;
        });
      }

      if (event.key === "ArrowRight") {
        setActiveImageIndex((prev) => {
          if (prev === null) return null;
          return (prev + 1) % displayedScenarioImages.length;
        });
      }
    };

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [displayedScenarioImages.length, isViewerOpen]);

  const goPreviousImage = () => {
    setActiveImageIndex((prev) => {
      if (prev === null) return null;
      return (prev - 1 + displayedScenarioImages.length) % displayedScenarioImages.length;
    });
  };

  const goNextImage = () => {
    setActiveImageIndex((prev) => {
      if (prev === null) return null;
      return (prev + 1) % displayedScenarioImages.length;
    });
  };

  const toggleCurrentImageInvalid = () => {
    if (!currentImage) return;

    setInvalidImageSources((prev) => {
      const next = new Set(prev);

      if (next.has(currentImage)) {
        next.delete(currentImage);
      } else {
        next.add(currentImage);
      }

      return next;
    });
  };

  const handleLoadingComplete = useCallback(() => {
    setIsLoadingSummary(false);
  }, []);

  if (isLoadingSummary) {
    return (
      <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
        <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4">
          <p className="text-2xl font-light leading-7 text-[#aaaaaa]">
            Projects
          </p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="truncate text-2xl font-light leading-7 text-[#aaaaaa]">
            {projectName}
          </p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="text-2xl font-light leading-7 text-[#eeeeee]">
            Run summary
          </p>
        </div>

        <ProcessingLoader
          phases={runSummaryLoadingPhases}
          durationMs={5200}
          onComplete={handleLoadingComplete}
        />
      </div>
    );
  }

  return (
    <>
      <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
        <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4">
          <p className="text-2xl font-light leading-7 text-[#aaaaaa]">
            Projects
          </p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="truncate text-2xl font-light leading-7 text-[#aaaaaa]">
            {projectName}
          </p>
          <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
          <p className="text-2xl font-light leading-7 text-[#eeeeee]">
            Run summary
          </p>
        </div>

        <div className="grid w-full gap-6 md:grid-cols-2 xl:grid-cols-4">
          {statCards.map((card, index) => (
            <article
              key={`${card.title}-${card.subtitle}-${card.value}`}
              style={{ animationDelay: `${140 + index * 30}ms` }}
              className="motion-interactive motion-page-enter flex items-start justify-between rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6"
            >
              <div>
                <div className="flex items-center gap-[7px] text-sm font-semibold leading-5 text-[#eeeeee]">
                  {card.attack ? (
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
                <p className="text-sm leading-5 text-[#aaaaaa]">
                  {card.subtitle}
                </p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-[2px] bg-[#222222] text-2xl font-light leading-6 text-[#eeeeee]">
                {card.value}
              </div>
            </article>
          ))}
        </div>

        <div className="motion-page-enter motion-delay-2 flex flex-col gap-3">
          <h2 className="text-sm font-semibold leading-5 text-[#eeeeee]">Attacks</h2>
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
              <h3 className="text-sm font-semibold leading-5 text-[#eeeeee]">
                Strongest
              </h3>
              <div className="mt-3 space-y-1">
                {strongestAttacks.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between text-sm leading-5"
                  >
                    <p className="text-[#aaaaaa]">{item.label}</p>
                    <p className="text-[#eeeeee]">{item.value}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
              <h3 className="text-sm font-semibold leading-5 text-[#eeeeee]">
                Weakest
              </h3>
              <div className="mt-3 space-y-1">
                {weakestAttacks.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between text-sm leading-5"
                  >
                    <p className="text-[#aaaaaa]">{item.label}</p>
                    <p className="text-[#eeeeee]">{item.value}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>

        <div className="motion-page-enter motion-delay-3 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold leading-5 text-[#eeeeee]">
              Scenarios
            </h2>
            <div className="flex items-center gap-2 text-sm">
              {(["failed", "passed"] as const).map((option) => {
                const selected = option === scenarioFilter;
                const label = option[0].toUpperCase() + option.slice(1);
                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setScenarioFilter(option)}
                    className={`motion-segment rounded-[8px] px-2 py-[0.3rem] ${
                      selected
                        ? "bg-[#1a1a1a] text-[#eeeeee]"
                        : "text-[#aaaaaa] hover:text-[#eeeeee]"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <section className="rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
            <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
              {displayedScenarioImages.map((src, index) => (
                <button
                  key={`${src}-${index}`}
                  type="button"
                  onClick={() => setActiveImageIndex(index)}
                  className="motion-interactive relative h-28 overflow-hidden rounded-[2px] text-left"
                >
                  <img
                    src={src}
                    alt="Failed scenario sample"
                    className={`motion-image h-full w-full object-cover ${
                      invalidImageSources.has(src) ? "opacity-[0.32]" : ""
                    }`}
                    loading="lazy"
                  />
                  {invalidImageSources.has(src) ? (
                    <span className="pointer-events-none absolute bottom-2 left-2 inline-flex h-4 items-center justify-center rounded-[2px] bg-[rgba(17,17,17,0.8)] px-1 text-center text-xs leading-3 text-[#eeeeee]">
                      Invalid
                    </span>
                  ) : null}
                  <div className="pointer-events-none absolute inset-0 rounded-[2px] border border-[rgba(255,255,255,0.2)]" />
                </button>
              ))}
              {remainingCount > 0 && (
                <div className="relative flex h-28 items-center justify-center overflow-hidden rounded-[2px] bg-[#222222] text-sm text-[#eeeeee]">
                  <span>...</span>
                  <div className="pointer-events-none absolute inset-0 rounded-[2px] border border-[rgba(255,255,255,0.2)]" />
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="flex items-center justify-between gap-3">
          <WizardBackButton
            onClick={() =>
              router.push(
                `/dashboard/projects/new/test-suite?projectName=${encodeURIComponent(
                  projectName.trim() || "New evaluation project"
                )}`
              )
            }
          />
          <button
            type="button"
            onClick={() =>
              router.push(
                `/dashboard/projects/new/fine-tuning?projectName=${encodeURIComponent(
                  projectName.trim() || "New evaluation project"
                )}`
              )
            }
            className="motion-interactive inline-flex min-h-9 items-center justify-center rounded-[8px] bg-[#fafafa] px-4 py-2 text-sm font-medium text-[#171717] transition-opacity hover:opacity-90"
          >
            Start fine-tuning
          </button>
        </div>
      </div>
      {isViewerOpen && currentImage ? (
        <div className="motion-page-enter fixed inset-0 z-50 bg-[rgba(17,17,17,0.94)] backdrop-blur-[70px]">
          <div className="mx-auto flex h-[100dvh] w-full max-w-[936px] flex-col gap-4 overflow-y-auto px-6 py-6">
            <div>
              <button
                type="button"
                onClick={() => setActiveImageIndex(null)}
                className="motion-interactive inline-flex h-8 items-center justify-center rounded-[8px] bg-[#222222] px-[10px] text-sm text-[#eeeeee]"
              >
                Back to summary
              </button>
            </div>

            <div className="flex min-h-0 flex-col gap-4">
              <div className="flex shrink-0 items-center justify-between gap-4">
                <button
                  type="button"
                  onClick={goPreviousImage}
                  className="motion-interactive inline-flex h-8 w-8 items-center justify-center rounded-[8px] border-2 border-[#222222] text-[#aaaaaa] transition-colors hover:text-[#eeeeee]"
                  aria-label="Previous failed scenario"
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>

                <div className="relative h-[min(44vh,550px)] max-h-[550px] overflow-hidden rounded-[2px]">
                  <img
                    src={currentImage}
                    alt="Failed scenario large preview"
                    className={`motion-image h-full w-full object-contain ${
                      isCurrentImageInvalid ? "opacity-[0.32]" : ""
                    }`}
                  />
                  {isCurrentImageInvalid ? (
                    <span className="pointer-events-none absolute bottom-2 left-2 inline-flex h-4 items-center justify-center rounded-[2px] bg-[rgba(17,17,17,0.8)] px-1 text-center text-xs leading-3 text-[#eeeeee]">
                      Invalid
                    </span>
                  ) : null}
                </div>

                <button
                  type="button"
                  onClick={goNextImage}
                  className="motion-interactive inline-flex h-8 w-8 items-center justify-center rounded-[8px] border-2 border-[#222222] text-[#aaaaaa] transition-colors hover:text-[#eeeeee]"
                  aria-label="Next failed scenario"
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              <div className="rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
                <div className="space-y-3 text-sm leading-5">
                  <div className="flex items-start justify-between gap-6">
                    <p className="text-[#aaaaaa]">Attacks</p>
                    <p className="text-right text-[#eeeeee]">
                      {currentScenario?.attacks ?? "Motion blur, compression, sensor noise"}
                    </p>
                  </div>
                  <div className="flex items-start justify-between gap-6">
                    <p className="text-[#aaaaaa]">Question</p>
                    <p className="text-right text-[#eeeeee]">
                      {currentScenario?.question ?? "How many engines are visible in this image?"}
                    </p>
                  </div>
                  <div className="flex items-start justify-between gap-6">
                    <p className="text-[#aaaaaa]">Correct response</p>
                    <p className="text-right text-[#eeeeee]">{currentScenario?.correct_response ?? "1"}</p>
                  </div>
                  {(() => {
                    const raw = currentScenario?.model_response ?? "";
                    const LIMIT = 120;
                    const isFailed = scenarioFilter === "failed";
                    const needsTruncation = isFailed && raw.length > LIMIT;
                    const display =
                      needsTruncation && !responseExpanded
                        ? raw.slice(0, LIMIT) + "..."
                        : raw;
                    return (
                      <div className="flex items-start justify-between gap-6">
                        <p className="shrink-0 text-[#aaaaaa]">Your model&apos;s response</p>
                        <div className="text-right">
                          <p className="text-[#eeeeee]">{display}</p>
                          {needsTruncation && (
                            <button
                              type="button"
                              onClick={() => setResponseExpanded((v) => !v)}
                              className="mt-1 text-xs text-[#aaaaaa] underline hover:text-[#eeeeee]"
                            >
                              {responseExpanded ? "Show less" : "Show more"}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={toggleCurrentImageInvalid}
                  className="inline-flex min-h-9 items-center justify-center rounded-[8px] bg-[#fafafa] px-4 py-2 text-sm font-medium text-[#171717]"
                >
                  {isCurrentImageInvalid ? "Mark valid" : "Mark invalid"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
