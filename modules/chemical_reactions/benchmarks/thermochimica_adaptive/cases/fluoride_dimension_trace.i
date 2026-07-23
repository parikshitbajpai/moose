!include multielement_fluoride.i

# Controlled dimension study: retain the same near-stoichiometric LiF carrier
# and add every other selected element at the same trace scale.  This separates
# algebraic dimension from the changing bulk chemistry of the MSRE trajectory.
[AuxKernels/F]
  function := '1.0*(1 + 0.002*(x + 0.0037*t - 0.5))'
[]
[AuxKernels/Li]
  function := '1.0*(1 - 0.002*(x + 0.0037*t - 0.5))'
[]
[ICs/F]
  function := '1.0*(1 + 0.002*(x - 0.5))'
[]
[ICs/Li]
  function := '1.0*(1 - 0.002*(x - 0.5))'
[]

# All non-carrier elements deliberately share a small trajectory.  Their
# presence increases the equilibrium dimension without changing the carrier.
[AuxKernels/Pu] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/U]  function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Th] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Nd] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Pr] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Ce] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/La] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Ba] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Cs] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/I]  function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Zr] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Y]  function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Sr] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Rb] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Ni] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Fe] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Cr] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/K]  function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Na] function := '1e-6*(1 + 0.001*(x + 0.0037*t - 0.5))' []
[AuxKernels/Be] function := '1e-6*(1 - 0.001*(x + 0.0037*t - 0.5))' []

[ICs/Pu] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/U]  function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Th] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Nd] function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Pr] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Ce] function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/La] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Ba] function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Cs] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/I]  function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Zr] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Y]  function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Sr] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Rb] function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Ni] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Fe] function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Cr] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/K]  function := '1e-6*(1 - 0.001*(x - 0.5))' []
[ICs/Na] function := '1e-6*(1 + 0.001*(x - 0.5))' []
[ICs/Be] function := '1e-6*(1 - 0.001*(x - 0.5))' []

[Outputs]
  file_base := fluoride_dimension_trace
[]
