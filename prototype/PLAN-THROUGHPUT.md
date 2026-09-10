# Throughput experiment plan

Updated 2026-09-10. Optimize measured diagnostic episode throughput while preserving
artifact integrity, exact context accounting and fresh verification containers.

## Source and measurement contract

Deploy a hashed snapshot of the released runtime, dispatcher and bridge together.
An experiment registration binds source hashes, task-pin hashes, served model revision,
runtime versions, compilation settings, concurrency, resource grants and budgets.
The Devstral revision is `55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128`.
Changing compilation or verification settings creates a separate measurement arm.
Never pool historical episodes across these changes.

Report attempted, terminal, admission-rejected, diagnostic pass/fail and unresolved
counts separately. Rejection is a retained outcome, not a fabricated failed test.
Throughput is actual terminal episodes and actual measured verdicts per elapsed
wall-clock hour, including stagger, dispatch, setup and verification. Also report
per-episode latency and token usage. Short-wave rates are observations, not sustained
capacity guarantees. No protected clean-solve rate follows from diagnostic pytest.

## A. Serving and launch overhead

1. Stagger every episode admission globally by three seconds; avoid simultaneous
   squashfs startup across both initial and replacement waves.
2. Start one free worker-5 GPU with compilation enabled, unchanged model revision,
   sampler, context length and 0.85 GPU-memory utilization. Set max-num-seqs to 16.
   Check readiness before launching the remaining free GPUs. Record effective
   settings; measure gains rather than inferring them from a bandwidth roofline.
3. Keep serving ports on loopback. Use one multiplexed SSH tunnel from the cluster
   control plane to worker-5. Episode dispatch itself creates no SSH handshakes. Pin the submitting SSH control
   connection to one login host: separate connections through the cluster alias may
   land on different hosts, whose loopback tunnels are not interchangeable.
4. Request two guest-dev nodes with 96 CPUs and 384 GiB each. Each episode reserves
   six CPUs and 17 GiB: a 2-CPU/1-GiB controller plus distinct 2-CPU/8-GiB source
   and fresh-verifier steps in the original lifecycle. All steps omit --overlap. The 1-CPU request
   observed in the placement probe still received two SMT siblings, so the
   dispatcher explicitly requests and accounts for two.
   Slurm selects CPU workers; model endpoints are independent of task placement.

## B. Artifact yield and accounting

Use bounded tracked-plus-untracked artifacts: capture regular source, binary and
backup files; record explicit exclusions for frozen declared reports, new candidate
tests and caches. Validate hashes, modes, exact delta coverage and fresh baselines.
Retain the artifact before refusing unsafe paths, unsupported changes or bounds.
All Git operations after candidate writes run inside the inherited kernel guard:
Git clean/smudge filters can execute repository code even during apply --check.

Do not add `--exclude-standard`: candidate-controlled ignore rules could hide
functional files. Do not relabel admission refusals as test failures to improve yield.
The original unknown episodes remain unknown when their full artifacts were lost.

Require Factory's supplementary semantic checks automatically. The saved near-miss
must fail despite passing the original suite; gold plus required new module and
binary payload must replay successfully. Keep the zero-model live receipts.

## C. Concurrency ramp

Initial K=3 and K=6 pilots exposed a placement defect: overlapping Slurm steps
assigned every controller to the same four CPUs and image unpackers to the same
two CPUs despite a 192-CPU allocation. Both pilots were stopped and remain separate,
interrupted records. This invalidates capacity inference from allocated CPU totals
alone.

The K4 measurement used 32 concurrent episodes, with non-overlapping
controller/source/verifier steps. At six CPUs per episode, it fits exactly within
192 CPUs; its 544-GiB peak reservation fits within the 768-GiB memory grant. A live
placement probe must confirm distinct CPU sets before launch. K=6 is rejected by
admission under this allocation. Use the same deterministic 48-task sample, record
every attempt and keep unknowns and admission refusals in the denominator.

Tool-command timeout returns exit 124 with bounded partial output after terminating
its process group; the model can continue within its remaining interaction budget.
Final-verifier timeout remains unknown even if partial output contains PASS lines.
This correction was validated with a live Linux probe before the corrected arm.

The shared interaction budget is 100 steps, 600 seconds and 1,024 output tokens per
call. This differs from the historical 50/300 pilot and must be registered explicitly.
Budget exhaustion is separate from test verdict; final replay has its own timeout.
Larger budgets were a fidelity correction, not a claimed throughput optimization.

## Final ten-minute control

K4 completed all 48 attempts in 1,488.45 seconds: 25 diagnostic verdicts
(12 pass, 13 fail), five admission rejections and 18 unknowns. Observed diagnostic
throughput was 60.47 verdicts/hour. Worker-12 produced 16 verdicts, four refusals
and four unknowns; worker-29 produced nine verdicts, one refusal and 14 unknowns.
All nine broker timeouts occurred on worker-29, which Slurm marked drained for
boot-disk pressure. Other verifier incompatibilities also contributed unknowns.

Request a fresh allocation of two guest-dev nodes without a requested or excluded
host list. Derive execution hosts from Slurm’s grant. Run a separate unperturbed
control across the same eight warm replicas. The source-release option lowers peak
reservation to four CPUs and 9 GiB by stopping the source after artifact admission
and durable capture, before starting the fresh verifier. With that option enabled,
K=6 permits 48 concurrent episodes in a 192-CPU grant; the default simultaneous source/verifier
lifecycle still reserves six CPUs and 17 GiB and caps this grant at 32. Keep all
48 tasks in their original registration
order regardless of earlier results. This is a fixed subset for throughput
inspection, not an estimate of the full candidate-pool base rate.
Do not restart serving or change sampling, context projection or verifier policy.

The arm has a 600-second dispatch-and-execution window followed by scoped cleanup.
Episode interaction budgets stay at 100 steps/600 seconds and final verification
retains its separate bounds. Work still running at the arm cutoff is censored as
unknown, never counted as a failed test. Report cleanup time separately and include
it in observed throughput. Preflight selected node health and remaining allocation
time; refuse unhealthy nodes rather than dispatching onto them. Registration must
record the actual two controller CPUs and selected source/verifier lifecycle.

Validate source handoff with zero-model tests: artifact validation and persistence
must precede source termination; termination failure prevents fresh replay; fresh
verification retains its distinct session, guarded Git operations and frozen checks.
Non-overlapping Slurm admission waits for source-step cleanup; it never bypasses
resource limits. Record handoff timing and artifact digest in per-episode receipts.

A later efficiency improvement is guarded gold compatibility preflight before
model spending. It must retain incompatible tasks in accounting, bind the exact
pin/runtime configuration and preserve all existing verifier checks. It is not
part of this final control.

## D. Cluster-local control plane

Run dispatcher and bridge on the cluster, with a bounded deadline and cleanup of
only owned process groups and Slurm steps. Pull the complete receipts back afterward.
Retain exact deployed-tokenizer projection and its ledger. Do not also add the
proposed persistent eviction floor: append-only message objects alone do not prove
prefix-stable chat-template tokenization across requests.

## Boundaries and follow-on work

Generic arbitrary-patch pytest evidence remains susceptible to candidate code in
its interpreter; package/environment mutations are not replayed. Protected mode
refuses before inference. This experiment explicitly selects diagnostic code-artifact
mode and cannot claim universal protected verification.

Training is a separate experiment requiring frozen pin/schema v2 before proposal
sampling. Stage-A format/diversity gains would not establish attack effectiveness.
It must not share episode receipts or silently consume the throughput allocation.

Keep prefix caching, exact tokenizer checks, output limits and image hash checks.
Do not pool containers, change tensor parallelism, sampler or context length, or
introduce speculative decoding during this comparison. None is needed to test the
registered throughput changes.
