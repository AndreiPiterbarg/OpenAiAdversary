"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";

import logo from "@/assets/logo.svg";

type LoadingPhase = {
  title: string;
  subtitle: string;
};

type ProcessingLoaderProps = {
  phases: LoadingPhase[];
  durationMs: number;
  onComplete: () => void;
};

export function ProcessingLoader({
  phases,
  durationMs,
  onComplete,
}: ProcessingLoaderProps) {
  const ghostRef = useRef<HTMLDivElement | null>(null);
  const safePhases = useMemo(
    () =>
      phases.length > 0
        ? phases
        : [
            {
              title: "Processing",
              subtitle: "Preparing your results...",
            },
          ],
    [phases]
  );
  const [progressRatio, setProgressRatio] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const startTime = Date.now();
    const progressTimer = window.setInterval(() => {
      const elapsed = Date.now() - startTime;
      const ratio = Math.min(elapsed / durationMs, 1);
      setProgressRatio(ratio);

      if (ratio >= 1) {
        window.clearInterval(progressTimer);
        setIsComplete(true);
      }
    }, 70);

    return () => window.clearInterval(progressTimer);
  }, [durationMs]);

  useEffect(() => {
    if (!isComplete) return;
    const completionTimer = window.setTimeout(onComplete, 180);
    return () => window.clearTimeout(completionTimer);
  }, [isComplete, onComplete]);

  useEffect(() => {
    const ghost = ghostRef.current;
    if (!ghost) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduceMotion.matches) {
      ghost.style.transform = "translate3d(0px, 0px, 0px)";
      return;
    }

    let frameId = 0;
    const loopDurationMs = 2600;
    const horizontalRadius = 72;
    const verticalRadius = 16;
    const cycleRate = (2 * Math.PI) / loopDurationMs;
    const startTime = performance.now();
    let hasAngleState = false;
    let previousTangentDegrees = 0;
    let continuousTangentDegrees = 0;
    let smoothedRotationDegrees = 0;

    const animate = (timestamp: number) => {
      const elapsed = timestamp - startTime;
      const theta = elapsed * cycleRate;

      const x = horizontalRadius * Math.sin(theta);
      const y = verticalRadius * Math.sin(2 * theta);

      const dx = horizontalRadius * cycleRate * Math.cos(theta);
      const dy = 2 * verticalRadius * cycleRate * Math.cos(2 * theta);
      const tangentDegrees = (Math.atan2(dy, dx) * 180) / Math.PI;

      if (!hasAngleState) {
        previousTangentDegrees = tangentDegrees;
        continuousTangentDegrees = tangentDegrees;
        smoothedRotationDegrees = tangentDegrees * 0.08;
        hasAngleState = true;
      } else {
        let delta = tangentDegrees - previousTangentDegrees;
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        continuousTangentDegrees += delta;
        previousTangentDegrees = tangentDegrees;
      }

      const wobbleDegrees =
        1.05 * Math.sin(1.9 * theta + 0.45) +
        0.55 * Math.sin(2.8 * theta + 1.1);
      const targetRotation = continuousTangentDegrees * 0.08 + wobbleDegrees;
      smoothedRotationDegrees += (targetRotation - smoothedRotationDegrees) * 0.16;

      const scale = 1 + 0.06 * Math.sin(2.2 * theta + 0.2);

      ghost.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(
        2
      )}px, 0) rotate(${smoothedRotationDegrees.toFixed(2)}deg) scale(${scale.toFixed(3)})`;

      frameId = window.requestAnimationFrame(animate);
    };

    frameId = window.requestAnimationFrame(animate);
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  const activePhaseIndex = Math.min(
    safePhases.length - 1,
    Math.floor(progressRatio * safePhases.length)
  );
  const activePhase = safePhases[activePhaseIndex];

  return (
    <section className="motion-page-enter motion-delay-2 flex min-h-[420px] items-center justify-center rounded-[8px] bg-[#141414] px-6 py-8 md:min-h-[620px]">
      <div className="flex w-full max-w-[560px] flex-col items-center gap-6">
        <div className="relative h-[64px] w-[220px]">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <div ref={ghostRef} className="ghost-path-sprite">
              <Image
                src={logo}
                alt=""
                aria-hidden
                width={20}
                height={24}
                className="dashboard-logo-filter h-6 w-5"
              />
            </div>
          </div>
        </div>

        <div className="flex w-full flex-col items-center gap-1 text-center">
          <p className="text-sm font-semibold leading-5 text-[#eeeeee]">
            {activePhase.title}
          </p>
          <p className="max-w-[320px] text-sm leading-5 text-[#aaaaaa]">
            {activePhase.subtitle}
          </p>
        </div>

      </div>
    </section>
  );
}
