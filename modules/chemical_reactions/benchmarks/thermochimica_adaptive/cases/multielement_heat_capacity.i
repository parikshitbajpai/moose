!include multielement_fluoride.i

# This variant is intentionally outside the core timing studies because the
# finite-difference heat-capacity output performs additional equilibria.
[ChemicalComposition/thermo/Outputs/SystemProperties]
  [system_heat_capacity]
    property = heat_capacity
  []
[]

[VectorPostprocessors/samples]
  variable := 'msfl_amount msfl_fraction gas_amount gas_fraction f_potential system_gibbs system_heat_capacity'
[]

[Outputs]
  file_base := multielement_heat_capacity
[]
