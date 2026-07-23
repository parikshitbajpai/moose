!include multielement_fluoride.i

# The database represents near-stoichiometric binary LiF with pure condensed
# phases rather than MSFL.  A charge-balanced FLiBe carrier is therefore used
# as the active-SUBQ qualification target and exact-fallback regression.
[ChemicalComposition/thermo]
  elements := 'Li Be F'
[]

[AuxKernels/temperature]
  function := '1000 + 30*(x + 0.0037*t)'
[]
[AuxKernels/F]
  function := '1.66*(1 + 0.001*(x + 0.0037*t - 0.5))'
[]
[AuxKernels/Be]
  function := '0.33*(1 + 0.001*(x + 0.0037*t - 0.5))'
[]
[AuxKernels/Li]
  function := '1.0*(1 + 0.001*(x + 0.0037*t - 0.5))'
[]
[ICs/temperature]
  function := '1000 + 30*x'
[]
[ICs/F]
  function := '1.66*(1 + 0.001*(x - 0.5))'
[]
[ICs/Be]
  function := '0.33*(1 + 0.001*(x - 0.5))'
[]
[ICs/Li]
  function := '1.0*(1 + 0.001*(x - 0.5))'
[]

[Outputs]
  file_base := flibe_msfl
[]
