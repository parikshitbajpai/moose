[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 200
    ny = 20
    xmax = 100
    ymax = 10
  []
[]

[GlobalParams]
  elements = 'Mo Ru'
  output_phases = 'BCCN HCPN'
  output_species = 'BCCN:Mo HCPN:Mo BCCN:Ru HCPN:Ru'
  output_element_potentials = 'mu:Mo mu:Ru'
  output_vapor_pressures = 'vp:gas_ideal:Mo'
  output_element_phases = 'ep:BCCN:Mo'
[]

[ChemicalComposition]
  thermofile = Kaye_NobleMetals.dat
  tunit = K
  punit = atm
  munit = moles
  temperature = Temperature
  output_species_unit = mole_fraction
  reinitialization_type = cache
  [Thermo]
  []
[]

[AuxVariables]
  [Temperature]
  []
[]

[Functions]
[Temperature]
  type = ParsedFunction
  expression = '1000.0 + 500.0*sin(0.5*t + x/100.0)'
[]
[]

[ICs]
  [Mo]
    type = FunctionIC
    variable = Mo
    # function = '0.8*(1-x)+4.3*x'
    function = '1.0 + cos(0.5*x)*cos(0.5*y)'
  []
  [Ru]
    type = FunctionIC
    variable = Ru
    # function = '0.2*(1-x)+4.5*x'
    function = '1.0 + sin(0.5*x)*sin(0.5*y)'
  []
[]

[AuxKernels]
  [Mo]
    type = FunctionAux
    variable = Temperature
    function = '1000.0 + 500.0*sin(0.5*t + 2.0*x/100.0)'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  # [Ru]
  #   type = FunctionAux
  #   variable = Ru
  #   function = '1.0 + sin(0.5*pi*x)*sin(0.5*pi*y)'
  #   execute_on = 'INITIAL'
  # []
[]

[Problem]
  solve = false
[]

[Executioner]
  type = Transient
  dt = 1.0
  end_time = 120
[]

[Outputs]
  exodus = true
  perf_graph = true
[]
