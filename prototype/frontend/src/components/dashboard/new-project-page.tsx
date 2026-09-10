"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { WizardBackButton } from "@/components/dashboard/wizard-back-button";

type SelectorKey = "model" | "dataset" | "task" | "duration";

type SelectorConfig = {
  title: string;
  options: string[];
};

type SelectionState = {
  model: string;
  dataset: string;
  task: string[];
  duration: string;
};

const normalizeTaskSelection = (value: unknown): string[] => {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
};

const pickValidSingleSelection = (
  value: unknown,
  validOptions: string[],
  fallback: string
): string => {
  if (Array.isArray(value)) {
    const match = value.find(
      (item): item is string =>
        typeof item === "string" && validOptions.includes(item)
    );
    return match ?? fallback;
  }

  if (typeof value === "string" && validOptions.includes(value)) {
    return value;
  }

  return fallback;
};

const migrateLegacyModelValue = (value: unknown): unknown => {
  if (value === "Mistral Large 3") {
    return "Mistral 3 Large";
  }
  return value;
};

const normalizeSelectionState = (value: unknown): SelectionState => {
  const maybeSelection = value as Partial<SelectionState> | null;

  const model = pickValidSingleSelection(
    migrateLegacyModelValue(maybeSelection?.model),
    selectorConfig.model.options,
    defaultSelection.model
  );
  const dataset = pickValidSingleSelection(
    maybeSelection?.dataset,
    selectorConfig.dataset.options,
    defaultSelection.dataset
  );
  const duration = pickValidSingleSelection(
    maybeSelection?.duration,
    selectorConfig.duration.options,
    defaultSelection.duration
  );
  const task = normalizeTaskSelection(maybeSelection?.task).filter((item) =>
    selectorConfig.task.options.includes(item)
  );

  return {
    model,
    dataset,
    duration,
    task: task.length > 0 ? task : defaultSelection.task
  };
};

const selectorConfig: Record<SelectorKey, SelectorConfig> = {
  model: {
    title: "Select a model",
    options: [
      "Ministral 3 14B",
      "Mistral 3 Large",
      "Llama-2-70b",
      "Codex-5.3",
      "Claude Opus 4.6",
      "Claude Sonnet 4.6"
    ]
  },
  dataset: {
    title: "Select a dataset",
    options: ["InfoVQA", "COCO", "ImageNet", "Open Images", "ADE20K", "Cityscapes"]
  },
  task: {
    title: "Select an attack profile",
    options: [
      "Object detection",
      "Semantic segmentation",
      "Image classification"
    ]
  },
  duration: {
    title: "Select run budget",
    options: ["Quick (10 min)", "Standard (30 min)", "Thorough (60 min)", "Extended (120 min)"]
  }
};

const fieldLabels: Record<SelectorKey, string> = {
  model: "Model",
  dataset: "Dataset",
  task: "Attack profile",
  duration: "Run budget"
};

const defaultSelection: SelectionState = {
  model: "Ministral 3 14B",
  dataset: "InfoVQA",
  task: ["Object detection", "Semantic segmentation"],
  duration: "Standard (30 min)"
};

type NewProjectPageProps = {
  initialProjectName?: string;
};

export function NewProjectPage({ initialProjectName }: NewProjectPageProps) {
  const router = useRouter();
  const selectorsContainerRef = useRef<HTMLDivElement>(null);
  const projectNameMeasureRef = useRef<HTMLSpanElement>(null);
  const [activeSelector, setActiveSelector] = useState<SelectorKey | null>(null);
  const [selection, setSelection] = useState<SelectionState>(defaultSelection);
  const [projectName, setProjectName] = useState(
    initialProjectName?.trim() || "Ministral Infographic Benchmark"
  );
  const [projectNameInputWidth, setProjectNameInputWidth] = useState(60);

  useEffect(() => {
    setSelection((prev) => normalizeSelectionState(prev));
  }, []);

  useLayoutEffect(() => {
    const measuredWidth = projectNameMeasureRef.current?.offsetWidth ?? 0;
    const nextWidth = Math.min(360, Math.max(60, Math.ceil(measuredWidth) + 2));
    setProjectNameInputWidth(nextWidth);
  }, [projectName]);

  useEffect(() => {
    if (!activeSelector) return;

    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (selectorsContainerRef.current?.contains(target)) return;
      setActiveSelector(null);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveSelector(null);
      }
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [activeSelector]);

  const normalizedSelection = normalizeSelectionState(selection);

  const onSelect = (key: SelectorKey, option: string) => {
    if (key === "task") {
      setSelection((prev) => {
        const currentTaskSelection = normalizeTaskSelection(prev.task);
        const nextTaskSelection = currentTaskSelection.includes(option)
          ? currentTaskSelection.filter((item) => item !== option)
          : [...currentTaskSelection, option];

        return {
          ...prev,
          task: nextTaskSelection
        };
      });
      return;
    }

    setSelection((prev) => ({
      ...prev,
      [key]: option
    }));
    setActiveSelector(null);
  };

  const getDisplayValue = (key: SelectorKey) => {
    if (key === "task") {
      return normalizedSelection.task.join(", ");
    }

    return normalizedSelection[key];
  };

  return (
    <div className="relative flex flex-col gap-6">
      <div className="motion-page-enter motion-delay-2 flex min-h-10 items-center gap-4 pr-6">
        <p className="text-2xl font-light leading-7 text-[#aaaaaa]">Projects</p>
        <ChevronDown className="h-4 w-4 text-[#aaaaaa]" />
        <p className="text-2xl font-light leading-7 text-[#eeeeee]">Create project</p>
      </div>

      <div className="motion-page-enter motion-delay-2 relative z-30 overflow-visible rounded-[8px] border border-[#222222] bg-[#1a1a1a] p-6">
        <div className="space-y-6" ref={selectorsContainerRef}>
          <div className="group flex items-center justify-between gap-6 text-sm leading-5">
            <p className="text-[#aaaaaa]">Project name</p>
            <div className="inline-flex items-center gap-2 rounded-[8px] pl-2 pr-1 py-1 text-right transition-[background-color] group-hover:bg-[#222222] focus-within:bg-[#222222]">
              <span
                ref={projectNameMeasureRef}
                aria-hidden
                className="pointer-events-none absolute opacity-0 whitespace-pre text-sm leading-5"
              >
                {projectName || " "}
              </span>
              <input
                type="text"
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                style={{ width: `${projectNameInputWidth}px` }}
                className="min-w-[60px] max-w-[360px] border-0 bg-transparent p-0 text-right text-sm leading-5 text-[#eeeeee] outline-none placeholder:text-[#777777]"
                aria-label="Project name"
              />
              <button
                type="button"
                onClick={() => setProjectName("")}
                aria-label="Clear project name"
                className="inline-flex h-4 w-4 items-center justify-center text-[#444444] transition-colors hover:text-[#eeeeee]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {(["model", "dataset", "task", "duration"] as const).map((key) => {
            const isActive = activeSelector === key;
            const config = selectorConfig[key];

            return (
              <div key={key} className="relative">
                <button
                  type="button"
                  onClick={() => {
                    setSelection((prev) => normalizeSelectionState(prev));
                    setActiveSelector((prev) => (prev === key ? null : key));
                  }}
                  className="group flex w-full items-center justify-between gap-6 text-sm leading-5"
                  aria-haspopup="menu"
                  aria-expanded={isActive}
                  aria-controls={`selector-menu-${key}`}
                >
                  <span className="text-[#aaaaaa]">{fieldLabels[key]}</span>
                  <span className="inline-flex items-center gap-2 rounded-[8px] pl-2 pr-1 py-1 text-right text-[#eeeeee] transition-[opacity,background-color] hover:opacity-85 group-hover:bg-[#222222]">
                    {getDisplayValue(key)}
                    <ChevronDown className="h-4 w-4 shrink-0 text-[#aaaaaa]" />
                  </span>
                </button>

                {isActive ? (
                  <div
                    id={`selector-menu-${key}`}
                    role="menu"
                    className="motion-page-enter absolute right-0 z-20 mt-2 w-max max-w-[calc(100vw-2rem)] overflow-hidden rounded-[10px] border border-[#2a2a2a] bg-[#171717] p-2 shadow-[0_14px_40px_rgba(0,0,0,0.45)]"
                  >
                    <div className="max-h-[220px] space-y-1 overflow-y-auto pr-1">
                      {config.options.map((option) => {
                        const selected =
                          key === "task"
                            ? normalizedSelection.task.includes(option)
                            : normalizedSelection[key] === option;

                        return (
                          <button
                            type="button"
                            key={option}
                            onClick={() => onSelect(key, option)}
                            className={cn(
                              "flex min-w-full items-center gap-2 rounded-[8px] px-2 py-1.5 text-left text-sm transition-colors",
                              selected
                                ? "bg-[#222222] text-[#eeeeee]"
                                : "text-[#aaaaaa] hover:bg-[#1f1f1f] hover:text-[#d0d0d0]"
                            )}
                            role="menuitemcheckbox"
                            aria-checked={selected}
                          >
                            <Check
                              className={cn(
                                "h-4 w-4 transition-opacity",
                                selected ? "opacity-100" : "opacity-0"
                              )}
                            />
                            <span className="whitespace-nowrap">{option}</span>
                          </button>
                        );
                      })}
                    </div>

                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <WizardBackButton onClick={() => router.push("/dashboard/projects")} />
        <button
          type="button"
          onClick={() =>
            router.push(
              `/dashboard/projects/new/test-suite?projectName=${encodeURIComponent(
                projectName.trim() || "New evaluation project"
              )}`
            )
          }
          className="motion-interactive inline-flex min-h-9 items-center justify-center rounded-[8px] bg-[#fafafa] px-4 py-2 text-sm font-medium text-[#171717] transition-opacity hover:opacity-90"
        >
          Continue to test suite
        </button>
      </div>
    </div>
  );
}
