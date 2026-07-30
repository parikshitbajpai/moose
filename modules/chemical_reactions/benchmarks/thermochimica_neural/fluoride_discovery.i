# Unrestricted ten-element discovery scan. The qualification driver supplies
# a Sobol state table and inspects the Exodus output to select active phases
# and species without relying on a gas-only phase restriction.
state_file = msfr_states.csv
state_count = 128

[GlobalParams]
  format = columns
[]

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = ${state_count}
    xmax = ${state_count}
  []
[]

[AuxVariables]
  [temperature] family = MONOMIAL order = CONSTANT []
  [pressure] family = MONOMIAL order = CONSTANT []
  [F] family = MONOMIAL order = CONSTANT []
  [Li] family = MONOMIAL order = CONSTANT []
  [U] family = MONOMIAL order = CONSTANT []
  [Th] family = MONOMIAL order = CONSTANT []
  [Ni] family = MONOMIAL order = CONSTANT []
  [Nd] family = MONOMIAL order = CONSTANT []
  [Ce] family = MONOMIAL order = CONSTANT []
  [La] family = MONOMIAL order = CONSTANT []
  [Cs] family = MONOMIAL order = CONSTANT []
  [I] family = MONOMIAL order = CONSTANT []
[]

[Functions]
  [temperature_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = temperature axis = x []
  [pressure_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = pressure axis = x []
  [F_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = F axis = x []
  [Li_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Li axis = x []
  [U_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = U axis = x []
  [Th_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Th axis = x []
  [Ni_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Ni axis = x []
  [Nd_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Nd axis = x []
  [Ce_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Ce axis = x []
  [La_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = La axis = x []
  [Cs_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Cs axis = x []
  [I_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = I axis = x []
[]

[AuxKernels]
  [temperature] type = FunctionAux variable = temperature function = temperature_table execute_on = INITIAL []
  [pressure] type = FunctionAux variable = pressure function = pressure_table execute_on = INITIAL []
  [F] type = FunctionAux variable = F function = F_table execute_on = INITIAL []
  [Li] type = FunctionAux variable = Li function = Li_table execute_on = INITIAL []
  [U] type = FunctionAux variable = U function = U_table execute_on = INITIAL []
  [Th] type = FunctionAux variable = Th function = Th_table execute_on = INITIAL []
  [Ni] type = FunctionAux variable = Ni function = Ni_table execute_on = INITIAL []
  [Nd] type = FunctionAux variable = Nd function = Nd_table execute_on = INITIAL []
  [Ce] type = FunctionAux variable = Ce function = Ce_table execute_on = INITIAL []
  [La] type = FunctionAux variable = La function = La_table execute_on = INITIAL []
  [Cs] type = FunctionAux variable = Cs function = Cs_table execute_on = INITIAL []
  [I] type = FunctionAux variable = I function = I_table execute_on = INITIAL []
[]

[ICs]
  [temperature] type = FunctionIC variable = temperature function = temperature_table []
  [pressure] type = FunctionIC variable = pressure function = pressure_table []
  [F] type = FunctionIC variable = F function = F_table []
  [Li] type = FunctionIC variable = Li function = Li_table []
  [U] type = FunctionIC variable = U function = U_table []
  [Th] type = FunctionIC variable = Th function = Th_table []
  [Ni] type = FunctionIC variable = Ni function = Ni_table []
  [Nd] type = FunctionIC variable = Nd function = Nd_table []
  [Ce] type = FunctionIC variable = Ce function = Ce_table []
  [La] type = FunctionIC variable = La function = La_table []
  [Cs] type = FunctionIC variable = Cs function = Cs_table []
  [I] type = FunctionIC variable = I function = I_table []
[]

[ChemicalComposition]
  [thermo]
    elements = 'F Li U Th Ni Nd Ce La Cs I'
    thermodynamic_database = ../thermochimica_adaptive/MSDTC_41_fluorides.dat
    evaluation_location = elemental
    temperature_unit = K
    pressure_unit = bar
    composition_unit = moles
    temperature = temperature
    pressure = pressure
    acceleration = exact
    warm_start = previous_solve
    batch_size = 256
    report_performance = true
    execute_on = INITIAL

    output_phases = ALL
    output_species = ALL
    species_output_unit = moles
    output_element_potentials = ALL
    output_vapor_pressures = ALL

    [Outputs]
      [SystemGibbsEnergies]
        [system_gibbs]
        []
      []
    []
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Steady
[]

[Outputs]
  file_base = fluoride_discovery
  csv = false
  exodus = true
  execute_on = FINAL
[]
