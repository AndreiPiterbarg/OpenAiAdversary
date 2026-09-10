"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { DashboardListPage } from "@/components/dashboard/dashboard-list";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

const uploadedModels = [
  { title: "Ministral 3 14B", subtitle: "Uploaded" },
  { title: "Mistral Large 3", subtitle: "Hosted via API" },
  { title: "Llama 3.1 70B", subtitle: "Uploaded" },
  { title: "Codex Vision QA", subtitle: "Hosted via API" },
  { title: "Claude Sonnet 4.6", subtitle: "Hosted via API" }
];

function DashboardModelsContent() {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<"uploaded" | "fine-tuned">(
    "uploaded"
  );

  useEffect(() => {
    const requestedTab = searchParams.get("tab");
    if (requestedTab === "fine-tuned") {
      setActiveTab("fine-tuned");
      return;
    }
    setActiveTab("uploaded");
  }, [searchParams]);

  const projectNames = [
    "Warehouse Safety Baseline",
    "Voxtral Night Shift Audit",
    "Retail Shelf Occlusion Study",
    "Autonomous Forklift Validation",
    "Perimeter Camera Stress Test",
    "Ministral 3 demo project"
  ];

  const baseModelNames = [
    "Ministral 3 14B",
    "Mistral Large 3",
    "Llama 3.1 70B",
    "Codex Vision QA",
    "Claude Sonnet 4.6"
  ];

  const fineTunedModels = useMemo(
    () => [
      {
        title: "Ministral 3 14B",
        subtitle: "Fine-tuned based on Ministral Infographic Benchmark",
        leadingGhostLogo: true
      },
      ...projectNames.map((projectName, index) => ({
        title:
          projectName === "Ministral 3 demo project"
            ? "Ministral 3 14B"
            : baseModelNames[index % baseModelNames.length],
        subtitle: `Fine-tuned based on ${projectName}`,
        leadingGhostLogo: true
      }))
    ],
    []
  );

  const displayedModels =
    activeTab === "fine-tuned" ? fineTunedModels : uploadedModels;

  return (
    <DashboardShell activeSection="models">
      <DashboardListPage
        title="Models"
        topRight={
          <div className="flex items-center gap-2 text-sm">
            <button
              type="button"
              onClick={() => setActiveTab("uploaded")}
              className={`motion-segment rounded-[8px] px-2 py-[0.3rem] ${
                activeTab === "uploaded"
                  ? "bg-[#1a1a1a] text-[#eeeeee]"
                  : "text-[#aaaaaa] hover:text-[#eeeeee]"
              }`}
            >
              Base
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("fine-tuned")}
              className={`motion-segment rounded-[8px] px-2 py-[0.3rem] ${
                activeTab === "fine-tuned"
                  ? "bg-[#1a1a1a] text-[#eeeeee]"
                  : "text-[#aaaaaa] hover:text-[#eeeeee]"
              }`}
            >
              Fine-tuned
            </button>
          </div>
        }
        ctaTitle="Add a model"
        ctaSubtitle="Upload or host via API"
        items={displayedModels}
      />
    </DashboardShell>
  );
}

export default function DashboardModelsPage() {
  return (
    <Suspense fallback={null}>
      <DashboardModelsContent />
    </Suspense>
  );
}
