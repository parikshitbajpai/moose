[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 100
    ny = 1
    xmax = 10
    ymax = 1
  []
[]

[GlobalParams]
  elements = 'F Li Be Zr U Pu Nd Pr Ce La Ba Cs I Y Sr Rb Th'
  output_phases = 'gas_ideal MSFL FM3M P3c1 Li2BeF4_S1(s) NdF3_S1(s)'
[]

[ChemicalComposition]
  [thermo]
    thermofile = MSTDB-TC_V3.0_Fluorides_No_Functions_8-2.dat
    tunit = K
    punit = Pa
    munit = moles
    temperature = T
    pressure = 185672.16
    output_species_unit = moles
    initial_values = debug_init.csv
    reinitialization_type = none
    is_fv = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]


[AuxVariables]
  [T]
    type = MooseVariableFVReal
  []
[]

[AuxKernels]
  [T]
    type = ParsedAux
    variable = T
    use_xyzt = true
    expression = '900.00+5.0*x'
    execute_on = 'INITIAL'
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Steady
[]

[Outputs]
  exodus = true
[]
