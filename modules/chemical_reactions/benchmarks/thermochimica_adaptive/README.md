# Adaptive Thermochimica benchmarks

This suite measures the cost and accuracy of the adaptive Thermochimica equilibrium executor. It
uses only databases distributed with the Chemical Reactions module and does not modify or persist
worker caches.

The three input problems are:

- `binary_smooth.i`: a single-phase Mo-Ru trajectory for interpolation and scaling studies;
- `binary_boundary.i`: a wider Mo-Ru trajectory crossing the BCC/HCP phase boundary; and
- `multielement_fluoride.i`: a depletion-like fluoride trajectory configurable from 2 to 22
  chemical elements.

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

The grids and repetition counts are stored in `manifests/smoke.json`, `quick.json`, and `full.json`.
Changing a study does not require modifying the driver.

## Results

Each run produces:

- `runs.csv`: one record per application repetition and Thermochimica execution stage;
- `accuracy.csv`: exact-versus-adaptive error statistics for every representative output;
- `failures.csv`: configurations that failed to launch or complete, without discarding other runs;
- `summary.csv`: median and interquartile-range query metrics;
- `metadata.json`: revision, platform, environment, package, and command information;
- `logs/` and `raw/`: application output and sampled state CSV files; and
- `figures/`: PNG and SVG scaling, accuracy, rejection, and cache plots.

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
