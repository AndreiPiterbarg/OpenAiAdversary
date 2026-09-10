"use client";

import { useCallback, useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ProcessingLoader } from "@/components/dashboard/processing-loader";

const previewPhases = [
  {
    title: "Fine-tuning your model!",
    subtitle:
      "Adapting weights from the failed scenarios to improve robustness against adversarial attacks.",
  },
  {
    title: "Validating improvements",
    subtitle:
      "Running evaluation passes to compare the original model against the fine-tuned model.",
  },
  {
    title: "Finalizing fine-tuning summary",
    subtitle:
      "Preparing effectiveness comparison metrics and latency impact for this run.",
  },
];

export function LoadingLabPage() {
  const [runId, setRunId] = useState(0);
  const [isAutoLooping, setIsAutoLooping] = useState(true);

  const handleLoadingComplete = useCallback(() => {
    if (!isAutoLooping) return;
    setRunId((previous) => previous + 1);
  }, [isAutoLooping]);

  const runLabel = useMemo(() => runId + 1, [runId]);

  return (
    <div className="motion-page-enter motion-delay-1 flex flex-col gap-6">
      <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4">
        <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Projects</p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Loading lab</p>
        <ChevronRight className="h-4 w-4 text-[#aaaaaa]" />
        <p className="text-2xl font-light leading-7 text-[#eeeeee]">Logo loop</p>
      </div>

      <div className="motion-page-enter motion-delay-2 flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-[#222222] bg-[#1a1a1a] px-4 py-3">
        <p className="text-sm leading-5 text-[#aaaaaa]">
          Current run: <span className="font-semibold text-[#eeeeee]">{runLabel}</span>
        </p>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-8 border-[#2a2a2a] bg-transparent px-3 text-xs text-[#eeeeee] hover:bg-[#222222] hover:text-[#fafafa]"
            onClick={() => setRunId((previous) => previous + 1)}
          >
            Replay now
          </Button>
          <Button
            type="button"
            className="h-8 bg-[#fafafa] px-3 text-xs text-[#171717] hover:bg-[#e5e5e5]"
            onClick={() => setIsAutoLooping((previous) => !previous)}
          >
            {isAutoLooping ? "Pause loop" : "Resume loop"}
          </Button>
        </div>
      </div>

      <ProcessingLoader
        key={`loading-lab-run-${runId}`}
        phases={previewPhases}
        durationMs={5600}
        onComplete={handleLoadingComplete}
      />
    </div>
  );
}
