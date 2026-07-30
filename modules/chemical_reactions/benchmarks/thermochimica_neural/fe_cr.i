[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 24
    ny = 24
  []
[]

[AuxVariables]
  [temperature]
    family = MONOMIAL
    order = CONSTANT
  []
  [pressure]
    family = MONOMIAL
    order = CONSTANT
  []
  [Fe]
    family = MONOMIAL
    order = CONSTANT
  []
  [Cr]
    family = MONOMIAL
    order = CONSTANT
  []
[]

[AuxKernels]
  [temperature]
    type = FunctionAux
    variable = temperature
    function = '1200 + 550*y'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  [pressure]
    type = ConstantAux
    variable = pressure
    value = 1
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  [chromium]
    type = FunctionAux
    variable = Cr
    function = '0.45 + 0.45*x'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  [iron]
    type = FunctionAux
    variable = Fe
    function = '0.55 - 0.45*x'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
[]

[ICs]
  [temperature]
    type = FunctionIC
    variable = temperature
    function = '1200 + 550*y'
  []
  [pressure]
    type = ConstantIC
    variable = pressure
    value = 1
  []
  [chromium]
    type = FunctionIC
    variable = Cr
    function = '0.45 + 0.45*x'
  []
  [iron]
    type = FunctionIC
    variable = Fe
    function = '0.55 - 0.45*x'
  []
[]

[ChemicalComposition]
  [thermo]
    elements = 'Fe Cr'
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
    surrogate_absolute_tolerances = 'bcc_amount:1e-6 fcc_amount:1e-6 hcp_amount:1e-6'
    surrogate_audit_interval = 20
    report_performance = true
    execute_on = INITIAL

    [Outputs]
      [ChemicalPotentials]
        [bcc_cr_potential]
          phase = BCC_A2
          species = CR:VA
        []
        [bcc_fe_potential]
          phase = BCC_A2
          species = FE:VA
        []
      []
      [ElementPotentials]
        [cr_potential]
          element = Cr
        []
        [fe_potential]
          element = Fe
        []
      []
      [Phases]
        [bcc_amount]
          phase = BCC_A2
        []
        [fcc_amount]
          phase = FCC_A1
        []
        [hcp_amount]
          phase = HCP_A3
        []
      []
      [SystemGibbsEnergies]
        [system_gibbs]
        []
      []
    []
  []
[]

[VectorPostprocessors]
  [samples]
    type = ElementValueSampler
    variable = 'temperature pressure Fe Cr bcc_cr_potential bcc_fe_potential cr_potential fe_potential bcc_amount fcc_amount hcp_amount system_gibbs'
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
  file_base = fe_cr
  csv = true
  exodus = false
  execute_on = FINAL
[]
