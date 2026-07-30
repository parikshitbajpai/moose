# Thermochimica neural surrogate prototype

The trainer consumes a CSV produced by an exact `ChemicalComposition` run and a JSON specification:

```bash
conda run -n ml python train_thermochimica_nn.py \
  --data exact.csv --spec model.json --output surrogate.pt
```

The TorchScript archive contains the input and output standardization and an embedded
`metadata.json`. The MOOSE input must request the same database, elements, units, phase selection,
and ordered outputs:

```text
acceleration = adaptive
surrogate_model = neural
surrogate_archive = surrogate.pt
```

Neural evaluation is restricted to the training bounds. States outside those bounds, predictions
that violate output invariants, and states selected for exact auditing are evaluated by
Thermochimica.

Run either reproducible demonstration with:

```bash
conda run -n ml python run_demo.py fe_cr --workdir /tmp/fe_cr_nn
conda run -n ml python run_demo.py fluoride_gas --workdir /tmp/fluoride_nn
```

The Fe-Cr case covers a smooth BCC region in temperature and Cr fraction. The fluoride case merges
the existing multielement benchmark with `fluoride_gas.i`, uses the gas-bearing
U-Zr-F-Be-Li trajectory over `x = 0..0.2`, and validates on a half-cell-shifted mesh. The restricted
domain is intentional: the longer trajectory crosses sharp thermodynamic regime changes and must
fall back to exact Thermochimica outside this archive.
