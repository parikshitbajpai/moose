# Table-driven controlled element-dimension study.  The benchmark driver
# supplies state_file, state_count, and the selected nested element set.
state_file = states.csv
state_count = 64

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
  [Pu] family = MONOMIAL order = CONSTANT []
  [U] family = MONOMIAL order = CONSTANT []
  [Th] family = MONOMIAL order = CONSTANT []
  [Nd] family = MONOMIAL order = CONSTANT []
  [Pr] family = MONOMIAL order = CONSTANT []
  [Ce] family = MONOMIAL order = CONSTANT []
  [La] family = MONOMIAL order = CONSTANT []
  [Ba] family = MONOMIAL order = CONSTANT []
  [Cs] family = MONOMIAL order = CONSTANT []
  [I] family = MONOMIAL order = CONSTANT []
  [Zr] family = MONOMIAL order = CONSTANT []
  [Y] family = MONOMIAL order = CONSTANT []
  [Sr] family = MONOMIAL order = CONSTANT []
  [Xe] family = MONOMIAL order = CONSTANT []
  [Ni] family = MONOMIAL order = CONSTANT []
  [Fe] family = MONOMIAL order = CONSTANT []
  [Cr] family = MONOMIAL order = CONSTANT []
  [K] family = MONOMIAL order = CONSTANT []
  [Na] family = MONOMIAL order = CONSTANT []
  [F] family = MONOMIAL order = CONSTANT []
  [Be] family = MONOMIAL order = CONSTANT []
  [Li] family = MONOMIAL order = CONSTANT []
[]

[Functions]
  [temperature_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = temperature axis = x []
  [pressure_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = pressure axis = x []
  [Pu_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Pu axis = x []
  [U_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = U axis = x []
  [Th_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Th axis = x []
  [Nd_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Nd axis = x []
  [Pr_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Pr axis = x []
  [Ce_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Ce axis = x []
  [La_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = La axis = x []
  [Ba_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Ba axis = x []
  [Cs_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Cs axis = x []
  [I_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = I axis = x []
  [Zr_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Zr axis = x []
  [Y_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Y axis = x []
  [Sr_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Sr axis = x []
  [Xe_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Xe axis = x []
  [Ni_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Ni axis = x []
  [Fe_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Fe axis = x []
  [Cr_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Cr axis = x []
  [K_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = K axis = x []
  [Na_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Na axis = x []
  [F_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = F axis = x []
  [Be_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Be axis = x []
  [Li_table] type = PiecewiseConstant data_file = ${state_file} x_title = x y_title = Li axis = x []
[]

[AuxKernels]
  [temperature] type = FunctionAux variable = temperature function = temperature_table execute_on = INITIAL []
  [pressure] type = FunctionAux variable = pressure function = pressure_table execute_on = INITIAL []
  [Pu] type = FunctionAux variable = Pu function = Pu_table execute_on = INITIAL []
  [U] type = FunctionAux variable = U function = U_table execute_on = INITIAL []
  [Th] type = FunctionAux variable = Th function = Th_table execute_on = INITIAL []
  [Nd] type = FunctionAux variable = Nd function = Nd_table execute_on = INITIAL []
  [Pr] type = FunctionAux variable = Pr function = Pr_table execute_on = INITIAL []
  [Ce] type = FunctionAux variable = Ce function = Ce_table execute_on = INITIAL []
  [La] type = FunctionAux variable = La function = La_table execute_on = INITIAL []
  [Ba] type = FunctionAux variable = Ba function = Ba_table execute_on = INITIAL []
  [Cs] type = FunctionAux variable = Cs function = Cs_table execute_on = INITIAL []
  [I] type = FunctionAux variable = I function = I_table execute_on = INITIAL []
  [Zr] type = FunctionAux variable = Zr function = Zr_table execute_on = INITIAL []
  [Y] type = FunctionAux variable = Y function = Y_table execute_on = INITIAL []
  [Sr] type = FunctionAux variable = Sr function = Sr_table execute_on = INITIAL []
  [Xe] type = FunctionAux variable = Xe function = Xe_table execute_on = INITIAL []
  [Ni] type = FunctionAux variable = Ni function = Ni_table execute_on = INITIAL []
  [Fe] type = FunctionAux variable = Fe function = Fe_table execute_on = INITIAL []
  [Cr] type = FunctionAux variable = Cr function = Cr_table execute_on = INITIAL []
  [K] type = FunctionAux variable = K function = K_table execute_on = INITIAL []
  [Na] type = FunctionAux variable = Na function = Na_table execute_on = INITIAL []
  [F] type = FunctionAux variable = F function = F_table execute_on = INITIAL []
  [Be] type = FunctionAux variable = Be function = Be_table execute_on = INITIAL []
  [Li] type = FunctionAux variable = Li function = Li_table execute_on = INITIAL []
[]

[ICs]
  [temperature] type = FunctionIC variable = temperature function = temperature_table []
  [pressure] type = FunctionIC variable = pressure function = pressure_table []
  [Pu] type = FunctionIC variable = Pu function = Pu_table []
  [U] type = FunctionIC variable = U function = U_table []
  [Th] type = FunctionIC variable = Th function = Th_table []
  [Nd] type = FunctionIC variable = Nd function = Nd_table []
  [Pr] type = FunctionIC variable = Pr function = Pr_table []
  [Ce] type = FunctionIC variable = Ce function = Ce_table []
  [La] type = FunctionIC variable = La function = La_table []
  [Ba] type = FunctionIC variable = Ba function = Ba_table []
  [Cs] type = FunctionIC variable = Cs function = Cs_table []
  [I] type = FunctionIC variable = I function = I_table []
  [Zr] type = FunctionIC variable = Zr function = Zr_table []
  [Y] type = FunctionIC variable = Y function = Y_table []
  [Sr] type = FunctionIC variable = Sr function = Sr_table []
  [Xe] type = FunctionIC variable = Xe function = Xe_table []
  [Ni] type = FunctionIC variable = Ni function = Ni_table []
  [Fe] type = FunctionIC variable = Fe function = Fe_table []
  [Cr] type = FunctionIC variable = Cr function = Cr_table []
  [K] type = FunctionIC variable = K function = K_table []
  [Na] type = FunctionIC variable = Na function = Na_table []
  [F] type = FunctionIC variable = F function = F_table []
  [Be] type = FunctionIC variable = Be function = Be_table []
  [Li] type = FunctionIC variable = Li function = Li_table []
[]

[ChemicalComposition]
  [thermo]
    elements = 'Li F'
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
    surrogate_relative_tolerance = 1e-3
    surrogate_absolute_tolerances = 'msfl_amount:1e-10 gas_amount:1e-10 msfl_fraction:1e-3 gas_fraction:1e-3 lif_fraction:1e-3 fli_vapor_pressure:1e-12'
    surrogate_audit_interval = 20
    report_performance = true
    execute_on = INITIAL

    [Outputs]
      [ElementPotentials]
        [f_potential] element = F []
        [li_potential] element = Li []
      []
      [Phases]
        [gas_amount] phase = gas_ideal []
        [gas_fraction] phase = gas_ideal unit = mole_fraction []
        [msfl_amount] phase = MSFL []
        [msfl_fraction] phase = MSFL unit = mole_fraction []
      []
      [Species]
        [lif_fraction] phase = MSFL species = LiF unit = mole_fraction []
      []
      [SystemGibbsEnergies]
        [system_gibbs]
        []
      []
      [VaporPressures]
        [fli_vapor_pressure] phase = gas_ideal species = FLi []
      []
    []
  []
[]

[VectorPostprocessors]
  [samples]
    type = ElementValueSampler
    variable = 'temperature pressure Pu U Th Nd Pr Ce La Ba Cs I Zr Y Sr Xe Ni Fe Cr K Na F Be Li f_potential li_potential gas_amount gas_fraction msfl_amount msfl_fraction lif_fraction system_gibbs fli_vapor_pressure'
    sort_by = id
    execute_on = FINAL
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Steady
[]

[Outputs]
  file_base = element_scaling
  csv = true
  exodus = false
  execute_on = FINAL
[]
