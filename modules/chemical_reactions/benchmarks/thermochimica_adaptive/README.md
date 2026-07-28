# Adaptive Thermochimica benchmarks

This suite measures the cost and accuracy of the adaptive Thermochimica equilibrium executor. It
uses only databases distributed with the Chemical Reactions module and does not modify or persist
worker caches.

The driver verifies the SHA-256 digest of each database required by the selected studies before
launching MOOSE. The MSTDB v4.1 fluoride database (`MSDTC_41_fluorides.dat`) is tracked explicitly
despite the repository-wide `*.dat` ignore rule so a recursive clone contains every production
input. MSTDB v4.1 does not include Rb; the dimension study uses K in the former Rb slot and adds
trace Xe only in its optional final group. The default representative trajectory drops the old Rb
inventory; the optional 22-element variant assigns Xe \(10^{-6}\) moles rather than reusing the Rb
amount.

The detailed physical definitions, study-to-case mapping, production launch inventory, expected
interpretation, and operator checklist are in
[`BENCHMARK_INVENTORY.md`](BENCHMARK_INVENTORY.md).

The mathematical definition, decision flowcharts, safeguards, and limitations of the implemented
algorithm are documented in `thermochimica_adaptive_acceleration.tex`. Build the technical note with
`latexmk -pdf thermochimica_adaptive_acceleration.tex` from this directory.

Set `ChemicalComposition/thermo/surrogate_model=kkt_linear` to benchmark the fixed-assemblage
sensitivity predictor and its ellipsoid metric. The driver records sensitivity construction time,
factorization failures, linear retrieves, ellipsoid updates, and Jacobian/metric storage alongside
the original `local_idw` telemetry.

Reader-facing reports use descriptive method names:

- **Full GEM**: complete Thermochimica Gibbs-energy minimization at every state;
- **Adaptive local interpolation**: validated inverse-distance interpolation from nearby exact
  equilibria; and
- **Adaptive KKT sensitivity**: a fixed-assemblage linear predictor based on equilibrium
  sensitivities.

Both adaptive methods use caching, auditing, and safeguarded Full GEM fallback. `adaptive` is an
execution mode rather than a separate algorithm and therefore does not appear as a headline
competitor.

The core performance and safety-regression input problems are:

- `binary_boundary.i` with driver-supplied bounds: the common-output Mo-Ru capability matrix;
- `binary_smooth.i`: a fixed-HCP Mo-Ru trajectory for interpolation and scaling studies;
- `binary_boundary.i`: a wider Mo-Ru trajectory crossing HCP, liquid, and BCC regimes;
- `multielement_fluoride.i`: the representative MSRE-derived 17-element chemistry, with an
  optional 22-element stress set;
- `fluoride_dimension_trace.i`: a fixed LiF carrier with trace additions for controlled dimension
  scaling;
- `lif_excess_f.i`: the historical gas-dominant F/Li=2.26 state-contamination regression;
- `lif_low_temperature.i`: near-stoichiometric binary Li-F with inactive MSFL; and
- `flibe_msfl.i`: a charge-balanced Li-Be-F carrier with active `SUBQ` MSFL.

The three Li-F/FLiBe inputs are safety regressions, not phase-model qualification tests. The MSTDB
database represents near-stoichiometric binary LiF with pure condensed phases, so the active-MSFL
fallback case uses FLiBe rather than labeling a non-MSFL binary state as molten salt. The current
nested MSRE element subsets are not used as a pure dimension study because removing cations while
retaining the complete fluorine inventory changes both stoichiometry and phase behavior.

The `active_subq_fallback` study intentionally uses 20 states with `warm_start=none`. It isolates
unsupported-`SUBQ` exact fallback from platform-sensitive previous-solve reinitialization and is
not a mesh-scaling or warm-start performance study. Its phase set is restricted to `MSFL` and
`gas_ideal`, so unrelated pure-phase searches cannot obscure the active-`SUBQ` behavior being
tested.

`multielement_heat_capacity.i` is an include-based variant used only by the optional full-tier
`output_cost` study. It isolates the additional equilibria required by heat-capacity output from
the core acceleration timings.

All cases evaluate constant monomial variables on a one-dimensional mesh. Consequently, `nx` is
the number of equilibrium states evaluated at each execution stage. The initial stage trains the
cache, the intermediate stage accounts for MOOSE execution ordering, and the last stage is the
shifted query used for post-warm-up metrics and sampled accuracy.

## Running

From the repository root, with a built Chemical Reactions executable:

```bash
conda run -n moose python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  validate --exe modules/chemical_reactions/chemical_reactions-opt

conda run -n moose python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  run --tier quick --study all \
  --exe modules/chemical_reactions/chemical_reactions-opt \
  --output /path/to/results

conda run -n moose python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  plot --input /path/to/results
```

The `smoke` tier is a functional check, `quick` is intended for local comparisons, and `full` is
the publication/performance tier. The full tier can take hours. Select one study with, for example,
`--study capability_comparison`, and use `--repetitions` or `--no-prime` for exploratory runs. MPI runs use
`mpiexec` by default; select a different launcher with `--mpiexec`.

The v4.1 fluoride database is much more costly for high-dimensional exact GEM solves than the
Mo-Ru database. Its quick/full meshes are intentionally smaller and stop at 17 elements; do not
infer their state counts from the Mo-Ru studies. A 22-element set remains available in the driver
as a manually budgeted stress case because a one-element-mesh exact run exceeded 15 minutes during
local qualification. The exact default grids are recorded in the manifests and explained in
`BENCHMARK_INVENTORY.md`.

Use `--study capability_comparison` for the fair exact-GEM, `local_idw`, and `kkt_linear`
comparison used by the headline visualizations. At the primary tolerance of \(10^{-4}\), quick
runs cover six Mo-Ru phase regimes at 1,000 states. Full runs cover the same six regimes at 1,000,
5,000, and 10,000 states and repeat the comparison at \(10^{-2}\), \(10^{-3}\), \(10^{-4}\), and
\(10^{-5}\). The driver supplies a non-grid-aligned query displacement and rejects a configuration
if its query coordinates overlap the populated cache coordinates exactly.

Fluoride state-isolation and unsupported-model fallback are reported by separate safety studies:
`fluoride_state_isolation`, `inactive_msfl_fallback`, and `active_subq_fallback`.

```bash
conda run -n moose python3 benchmark.py run \
  --tier quick --study capability_comparison \
  --exe ../../chemical_reactions-opt \
  --output /tmp/thermochimica-algorithms

conda run -n moose python3 benchmark.py report \
  --input /tmp/thermochimica-algorithms

conda run -n moose python3 benchmark.py plot \
  --input /tmp/thermochimica-algorithms
```

The grids and repetition counts are stored in `manifests/smoke.json`, `quick.json`, and `full.json`.
Changing a study does not require modifying the driver.

## INL HPC containers

INL HPC uses a versioned MOOSE development container. Follow the
[official installation instructions](https://mooseframework.inl.gov/getting_started/installation/inl_hpc_install_moose.html)
and derive the required module version from the checked-out source:

```bash
cd /home/bajpp/projects/tc_cache
module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$(./scripts/versioner.py moose-dev)"
MOOSE_DEV_MPI="${MOOSE_DEV_MPI:-mpich}"
MOOSE_DEV_MODULE="moose-dev-${MOOSE_DEV_MPI}"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"
moose-dev-shell

cd modules/chemical_reactions
METHOD=opt make -j 8
python3 ./run_tests --re thermochimica -j 4
exit
```

Validate from the host with a single containerized command:

```bash
moose-dev-exec python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  validate --exe modules/chemical_reactions/chemical_reactions-opt
```

The supplied `inl_hpc_full_array.slurm` and `inl_hpc_parallel.slurm` scripts resolve and record the
same container version automatically. Submit them from a login node with site-appropriate account
and scratch paths:

```bash
sbatch --wckey=YOUR_PROJECT \
  --export=ALL,TC_RESULTS=/scratch/$USER/tc-results \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/inl_hpc_full_array.slurm

sbatch --wckey=YOUR_PROJECT \
  --export=ALL,TC_RESULTS=/scratch/$USER/tc-results \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/inl_hpc_parallel.slurm
```

The batch scripts defer plotting so host Python does not need Matplotlib. Generate figures
afterward inside the container:

```bash
moose-dev-exec python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  plot --input /scratch/$USER/tc-results/RESULT_DIRECTORY
```

The full-array launcher defaults to Teton's `moose-dev-mpich` module and runs the Python driver
inside one `moose-dev-exec` invocation. All studies in that array are single-rank, so the MOOSE
subprocesses inherit the container environment without a per-command execution prefix. The
parallel-scaling launcher is separate: on Teton its host-side driver launches each application as
`srun -n N moose-dev-exec APPLICATION`. This uses Slurm to create ranks inside the allocation and
the public wrapper to enter the versioned container on every rank. The driver explicitly uses
host `/usr/bin/python3`; the module-selected Python may run in a container namespace that cannot
see the host `srun` path. Override `HOST_PYTHON`, `MOOSE_DEV_MPI`, or `MPI_LAUNCHER` only when the
selected cluster requires it, and never substitute an unversioned module. A study with no
successful configurations exits nonzero instead of leaving apparently successful header-only
result files.
The Teton launchers default `TC_REPO` to `/home/bajpp/projects/tc_cache`. Slurm standard output and
error files are written beneath the benchmark directory in `out/` and `err/`, respectively.
The full array requests one CPU and 32 GiB because its studies are serial; requesting additional
CPUs does not accelerate them. The parallel study requests 16 allocated CPUs and 64 GiB. Retain
`--exclusive` for publication timing, but remove it for inexpensive shakedown runs if node sharing
is acceptable. After a pilot, inspect `MaxRSS` with `sacct` and adjust memory with a safety margin.

## Results

Each run produces:

- `runs.csv`: one record per application repetition and Thermochimica execution stage;
- `accuracy.csv`: Full GEM-versus-accelerated-method error statistics for every representative
  output;
- `failures.csv`: configurations that failed to launch or complete, without discarding other runs;
- `summary.csv`: median and interquartile-range query metrics;
- `comparison.csv`: the correctness-gated, common capability table used by headline plots;
- `capability_gate.csv`: pass/fail verdicts and explicit failure reasons;
- `utilization.csv`: mutually exclusive query-state utilization fractions;
- `qualification.csv`: fluoride and Li-F coverage/fallback results;
- `report.md`: a concise human-readable result summary;
- `metadata.json`: revision, platform, environment, package, and command information;
- `logs/` and `raw/`: application output and sampled state CSV files; and
- `figures/`: publication-style PDF, SVG, and 300-DPI transparent PNG figures; and
- `figures/diagnostics/`: secondary scaling, rejection, cache, and execution diagnostics.

Measured repetitions are written atomically to `runs.csv`, `accuracy.csv`, `failures.csv`, and
`summary.csv` as soon as they finish. Consequently, a second terminal can regenerate partial plots
while a long study is still running:

```bash
conda run -n moose python3 benchmark.py plot --input /tmp/thermochimica-algorithms
```

The capability comparison produces separate wall-time and worker-time performance profiles for
each requested tolerance, an exact-call data profile, a work-precision plot, stacked state
utilization, and common tolerance curves. Invalid algorithms receive infinite profile cost but
remain in the denominator. Diagnostic plots from cache, warm-start, rejection, parallel, and
output-cost studies are written under `figures/diagnostics/`.

All figures load the tracked `report.mplstyle`, use a colorblind-safe and grayscale-distinguishable
method palette, place headline legends outside the data region, and export transparent PDF, SVG,
and 300-DPI PNG files. LaTeX text rendering is used when a `latex` executable is available and
falls back to Matplotlib text rendering otherwise.

Accuracy uses

\[
\frac{|\widehat y-y|}
{a+r\max(|\widehat y|,|y|)},
\]

where \(r\) is the requested relative tolerance. Before running either adaptive model, the driver
compares exact warm-start and exact cold-start results and sets \(a\) to the larger of ten times
their reproducibility difference and a floating-point precision floor. Any manifest overrides are
recorded explicitly. A capability result is accurate only if every sampled normalized error is at
most one and audit/restoration counters remain zero.

`worker_solve_time` isolates the Thermochimica worker, while `wall_time` includes process startup,
mesh setup, cache training, query evaluation, sampling, and output. The capability gate requires
valid sampled accuracy, at least 50% fewer exact GEM calls, and at least 2x total wall-time
speedup. Worker speedup is diagnostic and cannot by itself pass the gate.

Query-state utilization is partitioned into exact cache reuse, published surrogate results,
audited exact results, and exact fallback. `exact_solves / states` is reported separately because
cold retries can add GEM calls without adding evaluated states.

`matplotlib` is required for plots. If `psutil` is installed, the driver samples the aggregate
resident memory of the application process tree; otherwise the RSS field is empty. Thread and MPI
studies use a fixed total mesh size. Because adaptive caches remain worker-local, their hit counts
and exact solve counts are allowed to vary with the worker count.

By default a failed full-tier topology is recorded and the remaining configurations continue. Use
`--fail-fast` for debugging. This is particularly useful for worker-startup limitations that may
be platform-specific rather than silently omitting a requested thread or MPI point.
