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

The core performance and safety-regression input problems are:

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
`--study tolerance`, and use `--repetitions` or `--no-prime` for exploratory runs. MPI runs use
`mpiexec` by default; select a different launcher with `--mpiexec`.

The v4.1 fluoride database is much more costly for high-dimensional exact GEM solves than the
Mo-Ru database. Its quick/full meshes are intentionally smaller and stop at 17 elements; do not
infer their state counts from the Mo-Ru studies. A 22-element set remains available in the driver
as a manually budgeted stress case because a one-element-mesh exact run exceeded 15 minutes during
local qualification. The exact default grids are recorded in the manifests and explained in
`BENCHMARK_INVENTORY.md`.

Use `--study algorithm_comparison` for the balanced exact, `local_idw`, and `kkt_linear` matrix
used by the optimization-style visualizations. It is restricted to the fixed-HCP and
HCP-liquid-BCC Mo-Ru trajectories, where the `QKTO` model is eligible for KKT retrieval. Fluoride
state-isolation and unsupported-model fallback are reported by separate safety studies:
`fluoride_state_isolation`, `inactive_msfl_fallback`, and `active_subq_fallback`.

```bash
conda run -n moose python3 benchmark.py run \
  --tier quick --study algorithm_comparison \
  --exe ../../chemical_reactions-opt \
  --output /tmp/thermochimica-algorithms
```

The grids and repetition counts are stored in `manifests/smoke.json`, `quick.json`, and `full.json`.
Changing a study does not require modifying the driver.

## INL HPC containers

INL HPC uses a versioned MOOSE development container. Follow the
[official installation instructions](https://mooseframework.inl.gov/getting_started/installation/inl_hpc_install_moose.html)
and derive the required module version from the checked-out source:

```bash
cd /scratch/$USER/projects/tc_cache
module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$(./scripts/versioner.py moose-dev)"
module load "moose-dev-openmpi/${MOOSE_DEV_VERSION}"
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
sbatch --account=YOUR_PROJECT \
  --export=ALL,TC_REPO=/scratch/$USER/projects/tc_cache,TC_RESULTS=/scratch/$USER/tc-results \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/inl_hpc_full_array.slurm

sbatch --account=YOUR_PROJECT \
  --export=ALL,TC_REPO=/scratch/$USER/projects/tc_cache,TC_RESULTS=/scratch/$USER/tc-results \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/inl_hpc_parallel.slurm
```

The batch scripts defer plotting so host Python does not need Matplotlib. Generate figures
afterward inside the container:

```bash
moose-dev-exec python3 \
  modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py \
  plot --input /scratch/$USER/tc-results/RESULT_DIRECTORY
```

Do not substitute an unversioned `moose-dev-openmpi` module. The parallel script deliberately uses
`mpiexec -n N moose-dev-exec chemical_reactions-opt ...`, as required for containerized MPI jobs.

## Results

Each run produces:

- `runs.csv`: one record per application repetition and Thermochimica execution stage;
- `accuracy.csv`: exact-versus-adaptive error statistics for every representative output;
- `failures.csv`: configurations that failed to launch or complete, without discarding other runs;
- `summary.csv`: median and interquartile-range query metrics;
- `metadata.json`: revision, platform, environment, package, and command information;
- `logs/` and `raw/`: application output and sampled state CSV files; and
- `figures/`: PNG and SVG scaling, accuracy, rejection, and cache plots.

Measured repetitions are written atomically to `runs.csv`, `accuracy.csv`, `failures.csv`, and
`summary.csv` as soon as they finish. Consequently, a second terminal can regenerate partial plots
while a long study is still running:

```bash
conda run -n moose python3 benchmark.py plot --input /tmp/thermochimica-algorithms
```

The balanced comparison produces:

- `algorithm_performance_profiles`: Dolan-More-style worker and wall-time profiles;
- `algorithm_data_profile`: fraction of valid problems reached within an exact-GEM-call budget;
- `algorithm_work_precision`: query time and speedup versus maximum normalized error;
- `algorithm_speedup_heatmap`: median valid speedup by problem and surrogate;
- `algorithm_stage_learning`: exact-call fraction and cache growth from initial to query stage; and
- `phase_boundary_trajectory`: exact HCP/liquid/BCC fractions and surrogate error along the
  boundary path.

The profiles are correctness-gated. An adaptive result is valid only when its sampled maximum
error is within the requested relative tolerance and both its audit-failure and state-restoration
failure counts are zero. Invalid results remain in the work-precision plot but receive infinite
cost in performance and data profiles. Exact GEM is always the reference valid algorithm.

`worker_solve_time` isolates the Thermochimica worker, while `wall_time` includes process startup,
mesh setup, cache training, query evaluation, sampling, and output. Capability-gate fields use the
last/query-stage worker time: at least 50% fewer exact solves, a 2x worker speedup, and zero audit
failures. The gate is reported but does not stop a study.

`matplotlib` is required for plots. If `psutil` is installed, the driver samples the aggregate
resident memory of the application process tree; otherwise the RSS field is empty. Thread and MPI
studies use a fixed total mesh size. Because adaptive caches remain worker-local, their hit counts
and exact solve counts are allowed to vary with the worker count.

By default a failed full-tier topology is recorded and the remaining configurations continue. Use
`--fail-fast` for debugging. This is particularly useful for worker-startup limitations that may
be platform-specific rather than silently omitting a requested thread or MPI point.
