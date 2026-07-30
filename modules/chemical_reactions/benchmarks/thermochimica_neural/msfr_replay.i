# Exact/neural replay over an identical saved precursor field. The active
# output union below is the deterministic result of the unrestricted discovery
# scan; qualification rejects held-out states containing any unseen active
# phase or species.
flow_file = msfr_ns_precursor.e
F_value = 0.619994990289299
Li_value = 0.28686802725669447
U_value = 0.009280979260910028
Th_value = 0.07393795066662205
Ni_value = 0.009900990099009901
Nd_value = 0.0000029451427324207
Ce_value = 0.000006082077924437393
La_value = 0.000002190734620520621
Cs_value = 0.0000040215694693910555
I_value = 0.0000018229027178030577

[Mesh]
  coord_type = RZ
  [restart]
    type = FileMeshGenerator
    file = ${flow_file}
    use_for_exodus_restart = true
  []
[]

[AuxVariables]
  [temperature]
    family = MONOMIAL
    order = CONSTANT
    initial_from_file_var = T_fluid
  []
  [pressure]
    family = MONOMIAL
    order = CONSTANT
    initial_from_file_var = pressure
  []
  [radius]
    family = MONOMIAL
    order = CONSTANT
  []
  [axial_position]
    family = MONOMIAL
    order = CONSTANT
  []
[]

[AuxKernels]
  [radius]
    type = FunctionAux
    variable = radius
    function = x
    execute_on = INITIAL
  []
  [axial_position]
    type = FunctionAux
    variable = axial_position
    function = y
    execute_on = INITIAL
  []
[]

[ICs]
  [F] type = ConstantIC variable = F value = ${F_value} []
  [Li] type = ConstantIC variable = Li value = ${Li_value} []
  [U] type = ConstantIC variable = U value = ${U_value} []
  [Th] type = ConstantIC variable = Th value = ${Th_value} []
  [Ni] type = ConstantIC variable = Ni value = ${Ni_value} []
  [Nd] type = ConstantIC variable = Nd value = ${Nd_value} []
  [Ce] type = ConstantIC variable = Ce value = ${Ce_value} []
  [La] type = ConstantIC variable = La value = ${La_value} []
  [Cs] type = ConstantIC variable = Cs value = ${Cs_value} []
  [I] type = ConstantIC variable = I value = ${I_value} []
[]

[ChemicalComposition]
  [thermo]
    elements = 'F Li U Th Ni Nd Ce La Cs I'
    thermodynamic_database = ../thermochimica_adaptive/MSDTC_41_fluorides.dat
    evaluation_location = elemental
    temperature_unit = K
    pressure_unit = Pa
    composition_unit = moles
    temperature = temperature
    pressure = pressure
    acceleration = exact
    warm_start = previous_solve
    batch_size = 256
    surrogate_relative_tolerance = 1e-3
    surrogate_absolute_tolerances = 'solid_fli_amount:1e-10 msfl_amount:1e-10 ni_solid_amount:1e-10 u_solid_amount:1e-10 gas_amount:1e-10 solid_fli_fraction:1e-3 msfl_fraction:1e-3 ni_solid_fraction:1e-3 u_solid_fraction:1e-3 gas_fraction:1e-3'
    surrogate_audit_interval = 20
    report_performance = true
    execute_on = INITIAL

    [Outputs]
      [Phases]
        [solid_fli_amount] phase = 'FLi_LiF_FM3M_No.225(s)' []
        [solid_fli_fraction] phase = 'FLi_LiF_FM3M_No.225(s)' unit = mole_fraction []
        [msfl_amount] phase = MSFL []
        [msfl_fraction] phase = MSFL unit = mole_fraction []
        [ni_solid_amount] phase = 'Ni_fcc(s)' []
        [ni_solid_fraction] phase = 'Ni_fcc(s)' unit = mole_fraction []
        [u_solid_amount] phase = 'U_S1(s)' []
        [u_solid_fraction] phase = 'U_S1(s)' unit = mole_fraction []
        [gas_amount] phase = gas_ideal []
        [gas_fraction] phase = gas_ideal unit = mole_fraction []
      []
      [Species]
        [msfl_cef3] phase = MSFL species = CeF3 []
        [msfl_cei3] phase = MSFL species = CeI3 []
        [msfl_csf] phase = MSFL species = CsF []
        [msfl_csi] phase = MSFL species = CsI []
        [msfl_laf3] phase = MSFL species = LaF3 []
        [msfl_lai3] phase = MSFL species = LaI3 []
        [msfl_lif] phase = MSFL species = LiF []
        [msfl_lii] phase = MSFL species = LiI []
        [msfl_ndf3] phase = MSFL species = NdF3 []
        [msfl_ndi3] phase = MSFL species = NdI3 []
        [msfl_nif2] phase = MSFL species = NiF2 []
        [msfl_nii2] phase = MSFL species = NiI2 []
        [msfl_thf4] phase = MSFL species = ThF4 []
        [msfl_thi4] phase = MSFL species = ThI4 []
        [msfl_uf3] phase = MSFL species = UF3 []
        [msfl_u7f4] phase = MSFL species = 'U[CN=VII]F4' []
        [msfl_u7i4] phase = MSFL species = 'U[CN=VII]I4' []
        [msfl_u6f4] phase = MSFL species = 'U[CN=VI]F4' []
        [msfl_u6i4] phase = MSFL species = 'U[CN=VI]I4' []
        [msfl_u2f8] phase = MSFL species = 'U[Dimer]F8' []
        [msfl_u2i8] phase = MSFL species = 'U[Dimer]I8' []
        [gas_i] phase = gas_ideal species = I []
        [gas_i2] phase = gas_ideal species = I2 []
        [gas_uf5] phase = gas_ideal species = UF5 []
        [gas_uf6] phase = gas_ideal species = UF6 []
      []
      [ElementPotentials]
        [f_potential] element = F []
        [li_potential] element = Li []
        [u_potential] element = U []
        [th_potential] element = Th []
        [ni_potential] element = Ni []
        [nd_potential] element = Nd []
        [ce_potential] element = Ce []
        [la_potential] element = La []
        [cs_potential] element = Cs []
        [i_potential] element = I []
      []
      [VaporPressures]
        [i_vapor_pressure] phase = gas_ideal species = I []
        [i2_vapor_pressure] phase = gas_ideal species = I2 []
        [uf5_vapor_pressure] phase = gas_ideal species = UF5 []
        [uf6_vapor_pressure] phase = gas_ideal species = UF6 []
      []
      [ElementDistribution]
        [f_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = F unit = fraction []
        [f_in_msfl] phase = MSFL element = F unit = fraction []
        [f_in_ni_solid] phase = 'Ni_fcc(s)' element = F unit = fraction []
        [f_in_u_solid] phase = 'U_S1(s)' element = F unit = fraction []
        [f_in_gas] phase = gas_ideal element = F unit = fraction []
        [li_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Li unit = fraction []
        [li_in_msfl] phase = MSFL element = Li unit = fraction []
        [li_in_ni_solid] phase = 'Ni_fcc(s)' element = Li unit = fraction []
        [li_in_u_solid] phase = 'U_S1(s)' element = Li unit = fraction []
        [li_in_gas] phase = gas_ideal element = Li unit = fraction []
        [u_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = U unit = fraction []
        [u_in_msfl] phase = MSFL element = U unit = fraction []
        [u_in_ni_solid] phase = 'Ni_fcc(s)' element = U unit = fraction []
        [u_in_u_solid] phase = 'U_S1(s)' element = U unit = fraction []
        [u_in_gas] phase = gas_ideal element = U unit = fraction []
        [th_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Th unit = fraction []
        [th_in_msfl] phase = MSFL element = Th unit = fraction []
        [th_in_ni_solid] phase = 'Ni_fcc(s)' element = Th unit = fraction []
        [th_in_u_solid] phase = 'U_S1(s)' element = Th unit = fraction []
        [th_in_gas] phase = gas_ideal element = Th unit = fraction []
        [ni_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Ni unit = fraction []
        [ni_in_msfl] phase = MSFL element = Ni unit = fraction []
        [ni_in_ni_solid] phase = 'Ni_fcc(s)' element = Ni unit = fraction []
        [ni_in_u_solid] phase = 'U_S1(s)' element = Ni unit = fraction []
        [ni_in_gas] phase = gas_ideal element = Ni unit = fraction []
        [nd_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Nd unit = fraction []
        [nd_in_msfl] phase = MSFL element = Nd unit = fraction []
        [nd_in_ni_solid] phase = 'Ni_fcc(s)' element = Nd unit = fraction []
        [nd_in_u_solid] phase = 'U_S1(s)' element = Nd unit = fraction []
        [nd_in_gas] phase = gas_ideal element = Nd unit = fraction []
        [ce_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Ce unit = fraction []
        [ce_in_msfl] phase = MSFL element = Ce unit = fraction []
        [ce_in_ni_solid] phase = 'Ni_fcc(s)' element = Ce unit = fraction []
        [ce_in_u_solid] phase = 'U_S1(s)' element = Ce unit = fraction []
        [ce_in_gas] phase = gas_ideal element = Ce unit = fraction []
        [la_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = La unit = fraction []
        [la_in_msfl] phase = MSFL element = La unit = fraction []
        [la_in_ni_solid] phase = 'Ni_fcc(s)' element = La unit = fraction []
        [la_in_u_solid] phase = 'U_S1(s)' element = La unit = fraction []
        [la_in_gas] phase = gas_ideal element = La unit = fraction []
        [cs_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = Cs unit = fraction []
        [cs_in_msfl] phase = MSFL element = Cs unit = fraction []
        [cs_in_ni_solid] phase = 'Ni_fcc(s)' element = Cs unit = fraction []
        [cs_in_u_solid] phase = 'U_S1(s)' element = Cs unit = fraction []
        [cs_in_gas] phase = gas_ideal element = Cs unit = fraction []
        [i_in_solid_fli] phase = 'FLi_LiF_FM3M_No.225(s)' element = I unit = fraction []
        [i_in_msfl] phase = MSFL element = I unit = fraction []
        [i_in_ni_solid] phase = 'Ni_fcc(s)' element = I unit = fraction []
        [i_in_u_solid] phase = 'U_S1(s)' element = I unit = fraction []
        [i_in_gas] phase = gas_ideal element = I unit = fraction []
        [i_amount_in_gas] phase = gas_ideal element = I unit = moles []
      []
      [SystemGibbsEnergies]
        [system_gibbs]
        []
      []
    []
  []
[]

[Problem]
  solve = false
  allow_initial_conditions_with_restart = true
[]

[Executioner]
  type = Steady
[]

[Postprocessors]
  [integrated_gas_inventory]
    type = ElementIntegralVariablePostprocessor
    variable = gas_amount
    execute_on = FINAL
  []
  [integrated_iodine_gas_inventory]
    type = ElementIntegralVariablePostprocessor
    variable = i_amount_in_gas
    execute_on = FINAL
  []
[]

[Outputs]
  file_base = msfr_replay
  exodus = true
  csv = true
  execute_on = FINAL
[]
