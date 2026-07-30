# Thermochimica phase-aware neural surrogate qualification

The schema-2 trainer consumes disjoint exact training and validation CSVs plus a JSON
specification:

```bash
conda run -n ml python train_thermochimica_nn.py \
  --data training.csv --validation-data validation.csv \
  --spec model.json --output surrogate.pt
```

The TorchScript archive embeds standardization, physical output transforms, phase-presence
logits, bounded assemblage-stratified training-support anchors (4096 by default), and
`metadata.json`. The MOOSE input must request the same database, elements, units, phase
selection, and ordered outputs:

```text
acceleration = adaptive
surrogate_model = neural
surrogate_archive = surrogate.pt
```

Neural evaluation requires all of the following: finite canonical inputs inside the training
bounds; distance inside the calibrated radius for the predicted assemblage; at least 0.99 phase
confidence; agreement between phase labels and regressed phase amounts; and all declared scalar
and coupled invariants. Any failure, model error, or scheduled audit executes exact
Thermochimica.

Run the staged qualification driver with an external work directory:

```bash
conda run -n ml python qualification.py fe_cr --tier quick --workdir /tmp/tc_nn_fecr
conda run -n ml python qualification.py elements --tier quick --workdir /tmp/tc_nn_elements
conda run -n ml python qualification.py fluoride --tier quick --workdir /tmp/tc_nn_fluoride
conda run -n ml python qualification.py ns --tier quick --workdir /tmp/tc_nn_ns
```

Quick manifests use three timing repetitions and full manifests use seven. Each summary keeps
raw archive errors on the inaccessible test table separate from guarded MOOSE replay errors,
and reduces worker telemetry to numeric hit, fallback, audit, inference-time, worker-time, and
memory evidence. Generate the available phase-map, scaling, MSFR field-error, and iodine
inventory figures with:

```bash
conda run -n ml python plot_qualification.py \
  --workdir /tmp/tc_nn_campaign
```

The NS study uses `modules/combined/combined-opt` for both stages by default. For diagnosing a
combined-app build, the same workflow can use separate executables without changing the saved
field or replay contract:

```bash
conda run -n ml python qualification.py ns --tier quick --workdir /tmp/tc_nn_ns \
  --flow-app modules/navier_stokes/navier_stokes-opt \
  --replay-app modules/chemical_reactions/chemical_reactions-opt
```

`fe_cr_multiphase.i` covers the broad Fe-Cr BCC/FCC/HCP/liquid/sigma map.
`element_scaling.i` holds outputs fixed while the nested element set grows.
`fluoride_discovery.i` requests every phase and species for the ten-element MSFR envelope, and
`msfr_ns_precursor.i`/`msfr_replay.i` provide the self-contained one-way-coupled finite-volume
field study.

Submit the full INL campaign after creating a persistent work directory:

```bash
export TC_NN_WORKDIR=/scratch/$USER/tc-nn-results
mkdir -p "$TC_NN_WORKDIR"
sbatch inl_hpc_neural_array.slurm
```

The seven array tasks run Fe-Cr, unrestricted fluoride discovery, the combined-app NS study,
9/13/17-element scaling, and the separately labeled 22-element censored stress timing. The script
loads the version-matched `moose-dev` environment, activates `TC_ML_ENV` (`ml` by default), runs
the environment's Python inside `moose-dev-exec`, and passes `SLURM_CPUS_PER_TASK` to MOOSE through
`TC_NN_THREADS`. It records the source revision, module list, conda package lock, logs, raw tables,
archives, and compact summaries beneath `TC_NN_WORKDIR`.

The two rows in `msfr_compositions.csv` are derived from element-wise isotope sums in VTB's
`run_dep_out_in-core_number_densities.csv`: `fresh_proxy` uses the earliest available (5-day)
row, while `depleted` uses the final 30-day row. Both are normalized to unit total after adding
a declared local 1 mol% Ni corrosion inventory. The first row is therefore a fresh proxy, not a
zero-burnup state. The local field model, database, and Ni policy differ from VTB, so this
benchmark is inspired by that workflow and cannot reproduce its numerical values.

The original `fluoride_gas.i` trajectory is retained only as a legacy performance
microbenchmark. It is not evidence for general fluoride or multiphase capability.
