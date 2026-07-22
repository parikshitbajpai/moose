[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 200
  []
[]

[ChemicalComposition]
  [thermo]
    elements = 'Mo Ru'
    thermodynamic_database = ../../../test/tests/thermochimica/Kaye_NobleMetals.dat
    evaluation_location = elemental
    temperature_unit = K
    pressure_unit = atm
    composition_unit = moles
    temperature = 2250
    pressure = 1
    acceleration = adaptive
    warm_start = previous_solve
    surrogate_neighbors = 0
    surrogate_relative_tolerance = 1e-4
    surrogate_audit_interval = 100
    report_performance = true

    [Outputs]
      [Phases]
        [bcc_amount]
          phase = BCCN
        []
        [hcp_amount]
          phase = HCPN
        []
        [bcc_fraction]
          phase = BCCN
          unit = mole_fraction
        []
        [hcp_fraction]
          phase = HCPN
          unit = mole_fraction
        []
      []
      [ElementPotentials]
        [mo_potential]
          element = Mo
        []
      []
      [SystemGibbsEnergies]
        [system_gibbs]
        []
      []
    []
  []
[]

[AuxKernels]
  [mo]
    type = FunctionAux
    variable = Mo
    function = '0.2 + 0.6*x + 0.0037*t'
    execute_on = 'initial timestep_begin'
  []
  [ru]
    type = FunctionAux
    variable = Ru
    function = '0.8 - 0.6*x - 0.0037*t'
    execute_on = 'initial timestep_begin'
  []
[]

[ICs]
  [mo]
    type = FunctionIC
    variable = Mo
    function = '0.2 + 0.6*x'
  []
  [ru]
    type = FunctionIC
    variable = Ru
    function = '0.8 - 0.6*x'
  []
[]

[VectorPostprocessors]
  [samples]
    type = ElementValueSampler
    variable = 'Mo Ru bcc_amount hcp_amount bcc_fraction hcp_fraction mo_potential system_gibbs'
    sort_by = id
    execute_on = timestep_end
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Transient
  # The timestep-begin Thermochimica object executes before FunctionAux. The
  # second step therefore evaluates the state written during the first step.
  num_steps = 2
  dt = 1
[]

[Outputs]
  file_base = binary_boundary
  csv = true
  exodus = false
  execute_on = timestep_end
[]
