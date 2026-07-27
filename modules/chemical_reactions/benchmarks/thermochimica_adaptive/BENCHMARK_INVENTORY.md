# Adaptive Thermochimica benchmark inventory and run checklist

This document defines what each benchmark means, what it is intended to measure, and how to
interpret a production run. It deliberately distinguishes:

1. a **case**, which defines a thermochemical trajectory;
2. a **study**, which varies one numerical or physical parameter while running a case;
3. a **safety regression**, which verifies exact fallback or state isolation; and
4. a **qualification test**, which validates an implicit sensitivity against an exact-GEM
   finite-difference oracle.

The MOOSE fluoride safety cases are not sensitivity-qualification tests. They verify conservative
behavior while the relevant Thermochimica phase models remain unqualified.

## Common execution model

Every case uses elemental evaluation on a generated one-dimensional mesh. The coordinate
\(x\in[0,1]\) is a state generator, not a physical transport coordinate. With `nx = N`, each
Thermochimica execution stage evaluates \(N\) independent equilibrium states.

The cases use two transient steps because the Thermochimica object executes before the
`FunctionAux` objects at `timestep_begin`. The effective sequence is:

1. evaluate the initial-condition trajectory and populate the adaptive cache;
2. write the first displaced trajectory;
3. evaluate that displaced trajectory as the post-warm-up query.

The small time-dependent displacement prevents the query from being an identical-state cache
lookup. Application CSV files are written at `timestep_end`; thermochemical outputs therefore
correspond to the state available to Thermochimica at the beginning of that step.

Every adaptive configuration is paired with an exact
`warm_start = previous_solve` baseline. The driver reports both:

- `worker_solve_time`, which isolates work in the Thermochimica worker; and
- application wall time, which includes startup, mesh construction, packing, IPC, sampling, and
  output.

## Case catalog

### `binary_smooth.i`: fixed-HCP Mo-Ru trajectory

**Recommended presentation name:** Mo-Ru fixed-HCP smooth trajectory.

| Property | Definition |
| --- | --- |
| Database | `Kaye_NobleMetals.dat` |
| Elements | Mo, Ru |
| Temperature | 2250 K |
| Pressure | 1 atm |
| Composition unit | moles |
| Mo | \(0.2+0.1x+0.00037t\) |
| Ru | \(0.8-0.1x-0.00037t\) |
| Total amount | 1 mole |
| Recorded outputs | BCC/HCP amounts and fractions, Mo potential, system Gibbs energy |

The exact trajectory remains in a single HCP phase regime: the HCP fraction is one and the BCC
fraction is zero across the sampled interval. Both phases use the currently qualified `QKTO`
model.

This is the primary acceleration-performance case. It measures interpolation or linear-predictor
accuracy, tolerance dependence, cache warm-up, exact-call reduction, and best-case scaling without
an active-set change.

Expected interpretation:

- `local_idw` should accept many post-warm-up queries;
- `kkt_linear` should construct sensitivities and retrieve linear predictions;
- audited errors should satisfy the configured tolerance; and
- exact-call reduction and worker speedup should be substantial after warm-up.

### `binary_boundary.i`: Mo-Ru multi-regime traversal

**Recommended presentation name:** Mo-Ru HCP-liquid-BCC phase traversal.

| Property | Definition |
| --- | --- |
| Database | `Kaye_NobleMetals.dat` |
| Elements | Mo, Ru |
| Temperature | 2250 K |
| Pressure | 1 atm |
| Mo | \(0.2+0.6x+0.0037t\) |
| Ru | \(0.8-0.6x-0.0037t\) |
| Recorded phases | BCC, HCP, FCC, liquid, sigma |
| Other outputs | Mo potential and system Gibbs energy |

An exact 200-state scan of the final sampled trajectory produced the following approximate
regimes:

| Mo amount | Exact regime |
| ---: | --- |
| 0.209-0.500 | HCP |
| 0.503-0.578 | HCP + liquid |
| 0.581-0.620 | liquid |
| 0.623-0.698 | BCC + liquid |
| 0.701-0.806 | BCC |

FCC and sigma were inactive in this scan, but remain recorded so a changed database or trajectory
does not silently appear as "neither BCC nor HCP."

This is a boundary-safety case, not a best-case speed benchmark. It measures phase-token
rejections, geometry rejections, exact fallback near active-set changes, and audited accuracy.
A lower hit rate than the fixed-HCP case is expected and desirable near phase transitions.

### `multielement_fluoride.i`: representative MSRE-derived trajectory

**Recommended presentation name:** Representative multielement MSRE fluoride trajectory.

| Property | Definition |
| --- | --- |
| Database | `MSDTC_41_fluorides.dat` (MSTDB v4.1 fluorides) |
| Database elements | Pu U Th Gd Sm Nd Pr Ce La Ba Cs Xe I Pd Rh Ru Tc Mo Zr Y Sr Kr Ni Fe Cr K Ar Na Ne F Be Li He |
| Default representative elements | Pu U Th Nd Pr Ce La Ba Cs I Zr Y Sr K F Be Li |
| Optional 22-element stress set | default set + Ni Fe Cr Na Xe |
| Temperature | \(910+45q\) K |
| Pressure | \(185000+45000q\) Pa |
| Trajectory coordinate | \(q=x+0.0037t\) |
| Element amount | \(b_i[1+a_i(q-0.5)]\) |
| Coefficients | alternating signed 1%, 2%, 3%, and 4% slopes |
| Outputs | MSFL/gas amounts and fractions, F potential, system Gibbs energy |

The base composition comes from the bundled MSRE example. Major components include approximately
38.77 moles F, 17.19 moles Li, 7.72 moles Be, 1.32 moles Zr, and 0.211 moles U, together with
fission products and trace corrosion species. MSTDB v4.1 does not contain Rb, so the representative
trajectory drops the old Rb inventory. The optional 22-element stress variant adds Xe at
\(10^{-6}\) moles without interpreting the old Rb amount as a different element.

This case measures representative GEM cost and `local_idw` behavior when temperature, pressure,
and many elemental directions vary together. It is not a controlled dimension study.

The database includes `SUBQ`, `SUBL`, and other models that are not currently KKT-qualified.
Consequently, `kkt_linear` is expected to fail closed to exact GEM. That outcome measures
qualification coverage and fallback safety, not successful KKT acceleration.

MSTDB v4.1 is substantially more expensive than the former v3 database for the higher-dimensional
sets. The quick dimension study therefore uses 5 states and 4 neighbors; the full study uses 10
states and 4 neighbors. Both stop at the exercised 17-element set. The full
representative-fluoride model comparison uses 10 states, its parallel study uses 20, and the
output-cost study uses 5. The large-state-count scaling studies remain assigned to the much
cheaper Mo-Ru problem.

For launch planning, a local one-element-mesh exact initial/query sequence took approximately
0.4 s, 2.2 s, 6.3 s, 95-101 s, and 281 s for the 2-, 5-, 9-, 13-, and 17-element sets,
respectively. The 22-element sequence was stopped after 952 s while still using a full CPU core.
These measurements are hardware-specific qualification observations, not portable benchmark
results; cluster timings must be measured on the target nodes.

### `fluoride_dimension_trace.i`: trace-element dimension scaling

**Recommended presentation name:** LiF-carrier trace-element dimension scaling.

The carrier is kept near stoichiometric LiF:

\[
n_\mathrm{F}=1[1+0.002(q-0.5)], \qquad
n_\mathrm{Li}=1[1-0.002(q-0.5)].
\]

Every non-carrier element is assigned approximately \(10^{-6}\) moles and a small relative
trajectory. The nested element sets are:

| Dimension | Elements |
| ---: | --- |
| 2 | Li F |
| 5 | Li Be F Zr U |
| 9 | previous set + Nd Ce La Cs |
| 13 | previous set + I Pu K Sr |
| 17 | previous set + Ba Pr Th Y |
| 22 (manual stress case) | previous set + Ni Fe Cr Na Xe |

This case measures the scaling of GEM, cache lookup, Jacobian storage, and local validation with
thermochemical coordinate dimension. It is more controlled than removing elements from the MSRE
composition, but it is not a purely algebraic experiment: trace elements may introduce additional
candidate phases. K, the closest available alkali analogue, occupies the former Rb position in the
13-element set. Trace Xe is added in the final group so K is not duplicated and the 22-element
dimension remains available. A one-element-mesh 22-element exact run remained compute-bound for
more than 15 minutes during local qualification, so this point is excluded from the default quick
and full manifests. Run it only as an explicitly budgeted stress case.

### `lif_excess_f.i`: excess-F state-isolation reproducer

**Recommended presentation name:** Excess-F inactive-SUBQ state-isolation regression.

This case retains only Li and F from the MSRE-derived composition:

\[
n_\mathrm{F}\approx38.77,\qquad
n_\mathrm{Li}\approx17.19,\qquad
n_\mathrm{F}/n_\mathrm{Li}\approx2.26.
\]

It is intentionally not a physical LiF trajectory. The exact quick scan was gas-dominant, with
zero MSFL fraction and gas fractions of approximately 0.39-0.56.

The regression verifies that evaluating the inactive `SUBQ` MSFL model during sensitivity
inspection cannot mutate the state inherited by the next exact GEM solve. For `kkt_linear`, the
successful result is exact fallback with:

- positive `unsupported_model_rejections`;
- zero `state_restore_failures`; and
- exact results identical to a solve sequence without intervening sensitivity calls.

### `lif_low_temperature.i`: inactive-MSFL fallback

**Recommended presentation name:** Near-stoichiometric LiF inactive-MSFL fallback regression.

\[
n_\mathrm{F}=1[1+0.002(q-0.5)], \qquad
n_\mathrm{Li}=1[1-0.002(q-0.5)], \qquad
T=900+30q\ \mathrm{K}.
\]

Pressure follows the common 185-230 kPa trajectory. The exact quick scan had zero MSFL fraction
and at most a very small gas fraction. This case verifies exact fallback and state isolation while
an unqualified MSFL model is present but inactive.

It does not qualify `SUBQ`, and no KKT speedup is expected.

### `flibe_msfl.i`: active-SUBQ fallback

**Recommended presentation name:** Active-SUBQ FLiBe fallback regression.

\[
n_\mathrm{Li}=1.0,\qquad n_\mathrm{Be}=0.33,\qquad n_\mathrm{F}=1.66,
\]

with \(T=1000+30q\) K. The composition is approximately charge balanced because
\(n_\mathrm{Li}+2n_\mathrm{Be}=n_\mathrm{F}\). The exact quick scan had unit MSFL fraction and zero
gas fraction.

All three amounts receive almost the same relative displacement, so this trajectory mainly varies
temperature and total amount while preserving the Li-Be-F ratio. It verifies conservative exact
fallback for an active, unqualified `SUBQ` phase. It is not a sufficient derivative-qualification
trajectory because it does not span independent Li-Be-F composition directions.

### `multielement_heat_capacity.i`: derived-output cost

This includes the representative multielement fluoride case and requests system heat capacity.
Heat capacity performs additional equilibria in the current implementation, so it is intentionally
separated from core equilibrium timing.

The comparison measures how much cost comes from the converged equilibrium versus a derived output
that invokes additional solves.

## Full production-study inventory

The full tier uses seven measured repetitions and one unmeasured priming launch. Exact baselines
are reused within a study when their physical case and execution topology are identical.

| Study | Case | Varied quantity | Model(s) | Configurations | Application launches | Interpretation |
| --- | --- | --- | --- | ---: | ---: | --- |
| `tolerance` | fixed-HCP Mo-Ru | 9 tolerances, \(10^{-2}\) to \(10^{-6}\) | IDW | 9 | 80 | Accuracy/cost tradeoff in one regime |
| `mesh` | fixed-HCP Mo-Ru | 100 to 100,000 states | IDW | 7 | 112 | Scaling with state count |
| `elements` | LiF carrier + traces | 2, 5, 9, 13, 17 elements | IDW | 5 | 80 | Coordinate-dimension scaling |
| `fluoride_state_isolation` | excess-F reproducer | IDW versus KKT | both | 2 | 24 | Transactional state restoration |
| `inactive_msfl_fallback` | low-temperature LiF | IDW versus KKT | both | 2 | 24 | Inactive unsupported-model fallback |
| `active_subq_fallback` | active-MSFL FLiBe | IDW versus KKT | both | 2 | 24 | Active unsupported-model fallback |
| `neighbors` | fixed-HCP Mo-Ru | 2, 4, 8, automatic | IDW | 4 | 40 | Local-cloud cost and acceptance |
| `surrogate_model` | fixed-HCP Mo-Ru and representative fluoride | IDW versus KKT | both | 4 | 48 | Supported performance and coverage |
| `algorithm_comparison` | fixed-HCP and phase-traversal Mo-Ru | 4 tolerances and 2 models | both | 16 | 144 | Balanced performance profiles |
| `cache` | fixed-HCP Mo-Ru | 500 to 50,000 records | IDW | 4 | 40 | Capacity and saturation |
| `audit` | fixed-HCP Mo-Ru | intervals 0, 10, 100, 1000 | IDW | 4 | 40 | Audit overhead |
| `warm_start` | fixed-HCP Mo-Ru | four warm-start modes | exact | 4 | 32 | Exact GEM iteration reduction |
| `boundary` | Mo-Ru phase traversal | \(10^{-2},10^{-4},10^{-6}\) | IDW | 3 | 32 | Phase-boundary safety |
| `parallel` | Mo-Ru and representative fluoride | 1/2/4 threads or MPI ranks | IDW | 10 | 160 | Worker-local cache scaling |
| `output_cost` | representative fluoride | standard versus heat capacity | IDW | 2 | 32 | Derived-output overhead |

The full campaign contains 912 MOOSE application launches. The three fluoride safety studies are
reported separately from acceleration profiles. The balanced algorithm comparison is restricted
to the two `QKTO` Mo-Ru trajectories, where both surrogate models are eligible to operate.

## Interpretation groups

Do not combine every study into a single performance claim.

### Acceleration performance

Use:

- `tolerance`;
- `mesh`;
- `neighbors`;
- `cache`;
- `audit`;
- the fixed-HCP portion of `surrogate_model`; and
- `algorithm_comparison`.

Primary gates at relative tolerance \(10^{-4}\):

- at least 50% fewer exact GEM calls;
- at least 2x query-stage worker speedup;
- zero audit failures; and
- sampled normalized error no greater than one.

### Boundary safety

Use:

- `boundary`; and
- the phase-traversal portion of `algorithm_comparison`.

Success means exact fallback near phase transitions, zero audited violations, and no prediction
published across an incompatible assemblage. A reduced hit rate is not a failure.

### Qualification coverage and fallback safety

Use:

- `fluoride_state_isolation`;
- `inactive_msfl_fallback`;
- `active_subq_fallback`; and
- the representative fluoride portion of `surrogate_model`.

Success for an unsupported KKT model means exact results, positive unsupported-model telemetry,
and zero restoration or audit failures. It does not require speedup.

### Scaling and output cost

Use:

- `elements`;
- `parallel`; and
- `output_cost`.

Report worker time, wall time, exact-call count, cache occupancy, peak RSS, sensitivity storage,
and parallel efficiency separately.

## Production run checklist

### 1. Source and build

- [ ] Clone `agent/adaptive-thermochimica` with `--recurse-submodules`.
- [ ] Confirm the parent revision recorded in `metadata.json` is the intended revision.
- [ ] Confirm the Thermochimica submodule is at the intended sensitivity commit.
- [ ] Confirm the tracked MSTDB database passes the benchmark driver's SHA-256 preflight.
- [ ] Confirm `git status --porcelain` is empty, or archive the intentional diff.
- [ ] Activate the same named conda environment on every allocated node.
- [ ] Build `modules/chemical_reactions/chemical_reactions-opt`.
- [ ] Run the complete Thermochimica test group.
- [ ] Run `benchmark.py validate` before submitting the production array.

### 2. Cluster configuration

- [ ] Use persistent project or scratch storage, not node-local `/tmp`, for results.
- [ ] Record scheduler, partition, node type, CPU model, memory, and compiler/MPI versions.
- [ ] Disable dynamic CPU frequency policies if the cluster permits it, or record the policy.
- [ ] Request exclusive nodes for timing-sensitive production results.
- [ ] Avoid oversubscription and record process/thread affinity.
- [ ] Use one study per scheduler job or array element.
- [ ] Allocate four tasks for the `parallel` study, which contains up to four MPI ranks.
- [ ] Ensure the selected `--mpiexec` launcher accepts `-n`; `srun` does.
- [ ] Set a wall-time margin large enough for the priming launch and all seven repetitions.
- [ ] Confirm output quota can hold raw CSV files and logs for every repetition.

### 3. Exact physical scans

- [ ] Run the exact fixed-HCP Mo-Ru case and confirm HCP fraction remains one.
- [ ] Run the exact Mo-Ru traversal and archive its HCP/liquid/BCC regime map.
- [ ] Confirm FCC and sigma remain inactive or document any changed regime.
- [ ] Confirm the excess-F reproducer is gas-dominant and MSFL-inactive.
- [ ] Confirm low-temperature LiF is MSFL-inactive.
- [ ] Confirm FLiBe has active MSFL.
- [ ] Record complete assemblage tokens and complementarity diagnostics where available.
- [ ] Treat any newly observed active-set crossing as a boundary case, not a smooth case.

### 4. Manifest review

- [ ] Review `manifests/full.json` rather than assuming the default grid.
- [ ] Confirm seven repetitions and one priming launch are affordable.
- [ ] Confirm the mesh sizes match the intended strong- or fixed-size scaling interpretation.
- [ ] Confirm `algorithm_comparison` contains only mutually comparable phase-model coverage.
- [ ] Confirm safety regressions use `surrogate_audit_interval = 1`.
- [ ] Confirm the representative tolerance is \(10^{-4}\).
- [ ] Archive the exact manifest files with the results.

### 5. During execution

- [ ] Verify that `runs.csv`, `accuracy.csv`, and `summary.csv` grow after measured repetitions.
- [ ] Monitor `failures.csv`; an empty file contains only its header.
- [ ] Monitor scheduler logs for MPI launch, out-of-memory, or wall-time failures.
- [ ] Monitor disk usage from `raw/` and `logs/`.
- [ ] Plot partial results periodically without modifying the running result directory.
- [ ] Check that exact baselines are not being redundantly repeated within a study.
- [ ] Check that KKT fluoride runs report unsupported-model fallback rather than invalid retrievals.
- [ ] Check that no run reports `state_restore_failures > 0`.
- [ ] Check that no audited run reports `audit_failures > 0`.

### 6. Accuracy and safety review

- [ ] Confirm exact and adaptive sample counts and element IDs match.
- [ ] Confirm all outputs are finite.
- [ ] Confirm phase fractions lie in \([0,1]\).
- [ ] Confirm phase and gas amounts are nonnegative.
- [ ] Confirm every accepted result satisfies its configured normalized error.
- [ ] Inspect maximum, RMSE, and 95th-percentile errors by output rather than only aggregate error.
- [ ] Inspect boundary errors against the exact phase-fraction trajectory.
- [ ] Verify KKT mass-balance, positivity, conditioning, and complementarity rejection telemetry.
- [ ] Verify unsupported models return exact values.

### 7. Performance review

- [ ] Compare query-stage worker time separately from total wall time.
- [ ] Report medians and interquartile ranges across measured repetitions.
- [ ] Report exact GEM calls per query state.
- [ ] Report cache warm-up separately from post-warm-up performance.
- [ ] Report sensitivity construction time as part of KKT cost.
- [ ] Report cache entries, saturation, peak RSS, and sensitivity bytes.
- [ ] Apply the 50% exact-call and 2x worker-speedup gate only to eligible performance cases.
- [ ] Do not apply the speed gate to exact-fallback safety regressions.
- [ ] Report parallel efficiency and cache-hit behavior together.

### 8. Archival and reproducibility

- [ ] Preserve `metadata.json`, all manifests, scheduler scripts, and scheduler output.
- [ ] Preserve raw exact/adaptive sample CSV files for accepted publication points.
- [ ] Preserve application logs for failures and representative successful runs.
- [ ] Generate both PNG and SVG figures.
- [ ] Record whether Matplotlib and `psutil` were available.
- [ ] Record any failed topology rather than silently excluding it.
- [ ] Copy results from scratch storage to long-term storage before the retention deadline.
- [ ] Document excluded runs and the exclusion criterion.

## Known limitations

- Cache histories are worker-local, so hit counts can change with thread or MPI decomposition.
- The driver checkpoints completed repetitions but does not yet resume an interrupted study.
- The full-tier `algorithm_comparison` is balanced only over the currently qualified Mo-Ru
  systems; it is not evidence of KKT coverage for fluoride models.
- The trace-element dimension study can still activate new candidate phases.
- The FLiBe safety trajectory does not span independent composition directions.
- Heat capacity invokes additional equilibria and must remain separate from core GEM timing.
- Sampled accuracy and deterministic audits provide empirical safeguards, not a proof for every
  unaudited state.
