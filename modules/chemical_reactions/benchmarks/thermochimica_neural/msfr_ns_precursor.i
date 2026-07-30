# Self-contained, VTB-inspired finite-volume salt-channel precursor. Chemistry
# is deliberately one-way coupled in a separate replay input.
nx = 8
ny = 16
inlet_temperature = 900
flow_scale = 1
heat_scale = 1
outlet_pressure = 2e5
inlet_velocity = '${fparse 0.2 * flow_scale}'
power_density = '${fparse 2e6 * heat_scale}'

[Mesh]
  coord_type = RZ
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    xmin = 0
    xmax = 0.5
    ymin = 0
    ymax = 2
    nx = ${nx}
    ny = ${ny}
  []
[]

[Physics]
  [NavierStokes]
    [Flow]
      [flow]
        compressibility = incompressible
        velocity_variable = 'vel_r vel_z'
        density = rho
        dynamic_viscosity = mu
        initial_velocity = '0 ${inlet_velocity} 0'
        initial_pressure = ${outlet_pressure}

        inlet_boundaries = bottom
        momentum_inlet_types = fixed-velocity
        momentum_inlet_functors = '0 ${inlet_velocity}'

        wall_boundaries = 'left right'
        momentum_wall_types = 'symmetry noslip'

        outlet_boundaries = top
        momentum_outlet_types = fixed-pressure
        pressure_functors = ${outlet_pressure}

        mass_advection_interpolation = average
        momentum_advection_interpolation = average
      []
    []
    [FluidHeatTransfer]
      [energy]
        coupled_flow_physics = flow
        thermal_conductivity = k
        specific_heat = cp
        initial_temperature = ${inlet_temperature}

        energy_inlet_types = fixed-temperature
        energy_inlet_functors = ${inlet_temperature}
        energy_wall_types = 'heatflux heatflux'
        energy_wall_functors = '0 0'
        external_heat_source = power_density
        energy_advection_interpolation = average
      []
    []
  []
[]

[AuxVariables]
  [power_density]
    type = MooseVariableFVReal
    initial_condition = ${power_density}
  []
[]

[FunctorMaterials]
  [salt_properties]
    type = ADGenericFunctorMaterial
    prop_names = 'rho mu k cp'
    prop_values = '2000 0.005 1 2400'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
  nl_abs_tol = 1e-5
  nl_rel_tol = 1e-8
  nl_max_its = 50
  automatic_scaling = true
[]

[Outputs]
  file_base = msfr_ns_precursor
  exodus = true
[]
