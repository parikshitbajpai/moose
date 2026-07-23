!include multielement_fluoride.i

# Regression for the historical sensitivity-state contamination.  Removing the
# other MSRE elements leaves F/Li approximately 2.26 and a gas-dominant state
# with inactive SUBQ MSFL.  This is intentionally not a physical LiF benchmark.
[ChemicalComposition/thermo]
  elements := 'Li F'
[]

[Outputs]
  file_base := lif_excess_f
[]
