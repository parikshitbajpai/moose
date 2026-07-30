# Broad Fe-Cr phase-map qualification.  The default mesh is the production
# training grid; quick runs override nx and ny to 24.
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 64
    ny = 64
  []
[]

[AuxVariables]
  [temperature] family = MONOMIAL order = CONSTANT []
  [pressure] family = MONOMIAL order = CONSTANT []
  [Fe] family = MONOMIAL order = CONSTANT []
  [Cr] family = MONOMIAL order = CONSTANT []
[]

[AuxKernels]
  [temperature]
    type = FunctionAux
    variable = temperature
    function = '900 + 900*y'
    execute_on = INITIAL
  []
  [pressure]
    type = ConstantAux
    variable = pressure
    value = 1
    execute_on = INITIAL
  []
  [chromium]
    type = FunctionAux
    variable = Cr
    function = '0.02 + 0.96*x'
    execute_on = INITIAL
  []
  [iron]
    type = FunctionAux
    variable = Fe
    function = '0.98 - 0.96*x'
    execute_on = INITIAL
  []
[]

[ICs]
  [temperature] type = FunctionIC variable = temperature function = '900 + 900*y' []
  [pressure] type = ConstantIC variable = pressure value = 1 []
  [chromium] type = FunctionIC variable = Cr function = '0.02 + 0.96*x' []
  [iron] type = FunctionIC variable = Fe function = '0.98 - 0.96*x' []
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
    surrogate_absolute_tolerances = 'bcc_amount:1e-10 fcc_amount:1e-10 hcp_amount:1e-10 liquid_amount:1e-10 sigma_amount:1e-10 bcc_fraction:1e-3 fcc_fraction:1e-3 hcp_fraction:1e-3 liquid_fraction:1e-3 sigma_fraction:1e-3'
    surrogate_audit_interval = 20
    report_performance = true
    execute_on = INITIAL

    [Outputs]
      [ChemicalPotentials]
        [bcc_cr_potential] phase = BCC_A2 species = 'CR:VA' []
        [bcc_fe_potential] phase = BCC_A2 species = 'FE:VA' []
        [fcc_cr_potential] phase = FCC_A1 species = CR []
        [fcc_fe_potential] phase = FCC_A1 species = FE []
      []
      [ElementPotentials]
        [cr_potential] element = Cr []
        [fe_potential] element = Fe []
      []
      [Phases]
        [bcc_amount] phase = BCC_A2 []
        [bcc_fraction] phase = BCC_A2 unit = mole_fraction []
        [fcc_amount] phase = FCC_A1 []
        [fcc_fraction] phase = FCC_A1 unit = mole_fraction []
        [hcp_amount] phase = HCP_A3 []
        [hcp_fraction] phase = HCP_A3 unit = mole_fraction []
        [liquid_amount] phase = Structural_liquid []
        [liquid_fraction] phase = Structural_liquid unit = mole_fraction []
        [sigma_amount] phase = SIGD8Bsoln []
        [sigma_fraction] phase = SIGD8Bsoln unit = mole_fraction []
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
    variable = 'temperature pressure Fe Cr bcc_cr_potential bcc_fe_potential fcc_cr_potential fcc_fe_potential cr_potential fe_potential bcc_amount bcc_fraction fcc_amount fcc_fraction hcp_amount hcp_fraction liquid_amount liquid_fraction sigma_amount sigma_fraction system_gibbs'
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
  file_base = fe_cr_multiphase
  csv = true
  exodus = false
  execute_on = FINAL
[]
