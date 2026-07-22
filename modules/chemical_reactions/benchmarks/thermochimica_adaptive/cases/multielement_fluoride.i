[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 200
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
  # Declare the union once so the element list can be reduced from the command line.
  [Pu]
    family = MONOMIAL
    order = CONSTANT
  []
  [U]
    family = MONOMIAL
    order = CONSTANT
  []
  [Th]
    family = MONOMIAL
    order = CONSTANT
  []
  [Nd]
    family = MONOMIAL
    order = CONSTANT
  []
  [Pr]
    family = MONOMIAL
    order = CONSTANT
  []
  [Ce]
    family = MONOMIAL
    order = CONSTANT
  []
  [La]
    family = MONOMIAL
    order = CONSTANT
  []
  [Ba]
    family = MONOMIAL
    order = CONSTANT
  []
  [Cs]
    family = MONOMIAL
    order = CONSTANT
  []
  [I]
    family = MONOMIAL
    order = CONSTANT
  []
  [Zr]
    family = MONOMIAL
    order = CONSTANT
  []
  [Y]
    family = MONOMIAL
    order = CONSTANT
  []
  [Sr]
    family = MONOMIAL
    order = CONSTANT
  []
  [Rb]
    family = MONOMIAL
    order = CONSTANT
  []
  [Ni]
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
  [K]
    family = MONOMIAL
    order = CONSTANT
  []
  [Na]
    family = MONOMIAL
    order = CONSTANT
  []
  [F]
    family = MONOMIAL
    order = CONSTANT
  []
  [Be]
    family = MONOMIAL
    order = CONSTANT
  []
  [Li]
    family = MONOMIAL
    order = CONSTANT
  []
[]

[ChemicalComposition]
  [thermo]
    elements = 'Pu U Th Nd Pr Ce La Ba Cs I Zr Y Sr Rb Ni Fe Cr K Na F Be Li'
    thermodynamic_database = ../../../examples/MSRE/MSTDB-TC_V3.0_Fluorides_No_Functions_8-2.dat
    evaluation_location = elemental
    temperature_unit = K
    pressure_unit = Pa
    composition_unit = moles
    temperature = temperature
    pressure = pressure
    acceleration = adaptive
    warm_start = previous_solve
    surrogate_neighbors = 0
    surrogate_relative_tolerance = 1e-4
    surrogate_audit_interval = 100
    report_performance = true

    [Outputs]
      [Phases]
        [msfl_amount]
          phase = MSFL
        []
        [msfl_fraction]
          phase = MSFL
          unit = mole_fraction
        []
        [gas_amount]
          phase = gas_ideal
        []
        [gas_fraction]
          phase = gas_ideal
          unit = mole_fraction
        []
      []
      [ElementPotentials]
        [f_potential]
          element = F
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
  [temperature]
    type = FunctionAux
    variable = temperature
    function = '910 + 45*(x + 0.0037*t)'
    execute_on = 'initial timestep_begin'
  []
  [pressure]
    type = FunctionAux
    variable = pressure
    function = '185000 + 45000*(x + 0.0037*t)'
    execute_on = 'initial timestep_begin'
  []

  # The coefficients follow the element order in the thermodynamic database.
  [Pu]
    type = FunctionAux
    variable = Pu
    function = '1.38563215e-4*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [U]
    type = FunctionAux
    variable = U
    function = '2.10892804e-1*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Th]
    type = FunctionAux
    variable = Th
    function = '3.93608196e-12*(1 + 0.03*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Nd]
    type = FunctionAux
    variable = Nd
    function = '8.95117154e-5*(1 - 0.04*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Pr]
    type = FunctionAux
    variable = Pr
    function = '2.82638789e-5*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Ce]
    type = FunctionAux
    variable = Ce
    function = '9.22251044e-5*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [La]
    type = FunctionAux
    variable = La
    function = '3.56267015e-5*(1 + 0.03*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Ba]
    type = FunctionAux
    variable = Ba
    function = '4.00281036e-5*(1 - 0.04*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Cs]
    type = FunctionAux
    variable = Cs
    function = '1.00323048e-4*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [I]
    type = FunctionAux
    variable = I
    function = '4.60602134e-6*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Zr]
    type = FunctionAux
    variable = Zr
    function = '1.32254537*(1 + 0.03*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Y]
    type = FunctionAux
    variable = Y
    function = '2.89836954e-5*(1 - 0.04*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Sr]
    type = FunctionAux
    variable = Sr
    function = '5.87077753e-5*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Rb]
    type = FunctionAux
    variable = Rb
    function = '1.97168154e-5*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Ni]
    type = FunctionAux
    variable = Ni
    function = '1e-6*(1 + 0.03*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Fe]
    type = FunctionAux
    variable = Fe
    function = '1e-6*(1 - 0.04*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Cr]
    type = FunctionAux
    variable = Cr
    function = '1e-6*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [K]
    type = FunctionAux
    variable = K
    function = '1e-6*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Na]
    type = FunctionAux
    variable = Na
    function = '1e-6*(1 + 0.03*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [F]
    type = FunctionAux
    variable = F
    function = '3.87715483e1*(1 - 0.04*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Be]
    type = FunctionAux
    variable = Be
    function = '7.72254997*(1 + 0.01*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
  [Li]
    type = FunctionAux
    variable = Li
    function = '1.71906013e1*(1 - 0.02*(x + 0.0037*t - 0.5))'
    execute_on = 'initial timestep_begin'
  []
[]

[ICs]
  [temperature]
    type = FunctionIC
    variable = temperature
    function = '910 + 45*x'
  []
  [pressure]
    type = FunctionIC
    variable = pressure
    function = '185000 + 45000*x'
  []
  [Pu]
    type = FunctionIC
    variable = Pu
    function = '1.38563215e-4*(1 + 0.01*(x - 0.5))'
  []
  [U]
    type = FunctionIC
    variable = U
    function = '2.10892804e-1*(1 - 0.02*(x - 0.5))'
  []
  [Th]
    type = FunctionIC
    variable = Th
    function = '3.93608196e-12*(1 + 0.03*(x - 0.5))'
  []
  [Nd]
    type = FunctionIC
    variable = Nd
    function = '8.95117154e-5*(1 - 0.04*(x - 0.5))'
  []
  [Pr]
    type = FunctionIC
    variable = Pr
    function = '2.82638789e-5*(1 + 0.01*(x - 0.5))'
  []
  [Ce]
    type = FunctionIC
    variable = Ce
    function = '9.22251044e-5*(1 - 0.02*(x - 0.5))'
  []
  [La]
    type = FunctionIC
    variable = La
    function = '3.56267015e-5*(1 + 0.03*(x - 0.5))'
  []
  [Ba]
    type = FunctionIC
    variable = Ba
    function = '4.00281036e-5*(1 - 0.04*(x - 0.5))'
  []
  [Cs]
    type = FunctionIC
    variable = Cs
    function = '1.00323048e-4*(1 + 0.01*(x - 0.5))'
  []
  [I]
    type = FunctionIC
    variable = I
    function = '4.60602134e-6*(1 - 0.02*(x - 0.5))'
  []
  [Zr]
    type = FunctionIC
    variable = Zr
    function = '1.32254537*(1 + 0.03*(x - 0.5))'
  []
  [Y]
    type = FunctionIC
    variable = Y
    function = '2.89836954e-5*(1 - 0.04*(x - 0.5))'
  []
  [Sr]
    type = FunctionIC
    variable = Sr
    function = '5.87077753e-5*(1 + 0.01*(x - 0.5))'
  []
  [Rb]
    type = FunctionIC
    variable = Rb
    function = '1.97168154e-5*(1 - 0.02*(x - 0.5))'
  []
  [Ni]
    type = FunctionIC
    variable = Ni
    function = '1e-6*(1 + 0.03*(x - 0.5))'
  []
  [Fe]
    type = FunctionIC
    variable = Fe
    function = '1e-6*(1 - 0.04*(x - 0.5))'
  []
  [Cr]
    type = FunctionIC
    variable = Cr
    function = '1e-6*(1 + 0.01*(x - 0.5))'
  []
  [K]
    type = FunctionIC
    variable = K
    function = '1e-6*(1 - 0.02*(x - 0.5))'
  []
  [Na]
    type = FunctionIC
    variable = Na
    function = '1e-6*(1 + 0.03*(x - 0.5))'
  []
  [F]
    type = FunctionIC
    variable = F
    function = '3.87715483e1*(1 - 0.04*(x - 0.5))'
  []
  [Be]
    type = FunctionIC
    variable = Be
    function = '7.72254997*(1 + 0.01*(x - 0.5))'
  []
  [Li]
    type = FunctionIC
    variable = Li
    function = '1.71906013e1*(1 - 0.02*(x - 0.5))'
  []
[]

[VectorPostprocessors]
  [samples]
    type = ElementValueSampler
    variable = 'msfl_amount msfl_fraction gas_amount gas_fraction f_potential system_gibbs'
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
  file_base = multielement_fluoride
  csv = true
  exodus = false
  execute_on = timestep_end
[]
