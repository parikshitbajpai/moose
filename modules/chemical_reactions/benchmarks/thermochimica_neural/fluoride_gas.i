# Use the spatial initial-condition trajectory directly so every sampled input
# corresponds to the equilibrium state evaluated by Thermochimica.
[AuxKernels]
  active = ''
[]

[ChemicalComposition]
  [thermo]
    execute_on = INITIAL
  []
[]

[Executioner]
  type = Steady
[]

[VectorPostprocessors]
  [samples]
    type = ElementValueSampler
    variable = 'temperature pressure U Zr F Be Li f_potential gas_amount gas_fraction msfl_amount msfl_fraction system_gibbs'
    sort_by = id
    execute_on = FINAL
  []
[]

[Outputs]
  execute_on = FINAL
[]
