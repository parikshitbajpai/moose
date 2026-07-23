# ThermochimicaData

!syntax description /UserObjects/ThermochimicaData

## Description

`ThermochimicaData` performs the Thermochimica equilibrium calculations configured by the
[ChemicalComposition action](ChemicalCompositionAction.md). It evaluates the configured
temperature, pressure, and element compositions at each selected node or element and writes the
requested equilibrium quantities to the auxiliary variables created by the action.

In adaptive mode, each isolated worker retains exact states in a bounded `ValueCache`, reuses
homogeneous exact matches, and performs phase-aware local interpolation when its configured error
and invariant checks pass. The optional `kkt_linear` model instead stores fixed-assemblage output
sensitivities and uses a first-order prediction inside a validated ellipsoid of accuracy. Rejected
and audited states are evaluated exactly. Sensitivity trials restore a captured converged state
instead of recomputing inactive phases, preventing trial evaluations from seeding later GEM solves.
Only upstream-qualified phase-model combinations are eligible for linear retrieval.

Available quantities include amounts and fractions, element and thermodynamic-component
potentials, vapor pressures, phase Gibbs energies and driving forces, and the integral system Gibbs
energy. See [ChemicalCompositionAction.md#thermochemical-outputs] for their units and selection
syntax.

This object is created internally by `ChemicalComposition` and is not intended to be added directly
to the `[UserObjects]` block. Configure its evaluation location, outputs, batching, warm-start
strategy, block restriction, and execution schedule through the action parameters.

## Performance benchmarks

The adaptive Thermochimica benchmark suite in
`modules/chemical_reactions/benchmarks/thermochimica_adaptive` provides reproducible smooth,
phase-boundary, controlled chemical-dimension, Li-F state-isolation, active-MSFL, mesh, cache,
tolerance, and parallel scaling studies. It
records exact/adaptive accuracy and worker telemetry separately from whole-application wall time.

!syntax inputs /UserObjects/ThermochimicaData

!syntax children /UserObjects/ThermochimicaData
