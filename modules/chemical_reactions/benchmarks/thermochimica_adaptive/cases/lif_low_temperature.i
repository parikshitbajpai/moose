!include multielement_fluoride.i

# Near-stoichiometric LiF below the melting region.  This exercises exact
# fallback while the unqualified MSFL model is inactive.
[ChemicalComposition/thermo]
  elements := 'Li F'
[]

[AuxKernels/temperature]
  function := '900 + 30*(x + 0.0037*t)'
[]
[AuxKernels/F]
  function := '1.0*(1 + 0.002*(x + 0.0037*t - 0.5))'
[]
[AuxKernels/Li]
  function := '1.0*(1 - 0.002*(x + 0.0037*t - 0.5))'
[]
[ICs/temperature]
  function := '900 + 30*x'
[]
[ICs/F]
  function := '1.0*(1 + 0.002*(x - 0.5))'
[]
[ICs/Li]
  function := '1.0*(1 - 0.002*(x - 0.5))'
[]

[Outputs]
  file_base := lif_low_temperature
[]
