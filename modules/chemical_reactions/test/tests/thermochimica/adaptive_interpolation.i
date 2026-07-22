[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 20
  []
[]

[ChemicalComposition]
  [thermo]
    elements = 'Mo Ru'
    thermodynamic_database = Kaye_NobleMetals.dat
    temperature_unit = K
    pressure_unit = atm
    composition_unit = moles
    temperature = 2250
    output_phases = 'BCCN HCPN'
    acceleration = adaptive
    surrogate_neighbors = 2
    surrogate_relative_tolerance = 10
    surrogate_audit_interval = 0
    report_performance = true
  []
[]

[AuxKernels]
  [mo]
    type = FunctionAux
    variable = Mo
    function = '0.2 + 0.6*x + 0.01*t'
    execute_on = 'initial timestep_begin'
  []
  [ru]
    type = FunctionAux
    variable = Ru
    function = '0.8 - 0.6*x - 0.01*t'
    execute_on = 'initial timestep_begin'
  []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Transient
  num_steps = 1
  dt = 1
[]

[Outputs]
  exodus = false
[]
