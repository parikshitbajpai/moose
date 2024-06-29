//* This file is part of the MOOSE framework
//* https://www.mooseframework.org
//*
//* All rights reserved, see COPYRIGHT for full restrictions
//* https://github.com/idaholab/moose/blob/master/COPYRIGHT
//*
//* Licensed under LGPL 2.1, please see LICENSE for details
//* https://www.gnu.org/licenses/lgpl-2.1.html

#pragma once

// MOOSE includes
#include "NodalUserObject.h"
#include "ElementUserObject.h"
#include "ValueCache.h"

#ifdef THERMOCHIMICA_ENABLED
#include "Thermochimica-cxx.h"
#endif

// Forward declaration
class ChemicalCompositionAction;

template <bool is_nodal>
using ThermochimicaDataBaseParent =
    typename std::conditional<is_nodal, NodalUserObject, ElementUserObject>::type;

/**
 * User object that performs a Gibbs energy minimization at each node by
 * calling the Thermochimica code. This object can only be added through
 * the ChemicalCompositionAction which also sets up the variables for the
 * calculation.
 */
template <bool is_nodal>
class ThermochimicaDataBase : public ThermochimicaDataBaseParent<is_nodal>
{
public:
  static InputParameters validParams();
  ThermochimicaDataBase(const InputParameters & parameters);
  ~ThermochimicaDataBase();

  virtual void initialize() override;
  virtual void execute() override;
  virtual void finalize() override {}
  virtual void threadJoin(const UserObject &) override {}

  /**
   * Function to get re-initialization data from Thermochimica and save
   * it in member variables of this UserObject.
   */
  void getReinitializationData();

  /**
   * Function to load re-initialization data saved in this UserObject
   * back into Thermochimica.
   */
  void setReinitializationData();

  const Thermochimica::ReinitializationData & getNodalData(dof_id_type id) const;
  const Thermochimica::ReinitializationData & getElementData(dof_id_type id) const;

  // universal data access
  const Thermochimica::ReinitializationData & getData(dof_id_type id) const;

protected:
  // child process routine to dispatch thermochimica calculations
  void server();

  // helper to wait on a socket read
  template <typename T>
  void expect(T expect_msg);

  // send message to socket
  template <typename T>
  void notify(T send_msg);

  void getEquilibrium();

  void currentStateSpace();

  const VariableValue & _pressure;
  const VariableValue & _temperature;

  const std::size_t _n_phases;
  const std::size_t _n_species;
  const std::size_t _n_elements;
  const std::size_t _n_vapor_species;
  const std::size_t _n_phase_elements;
  const std::size_t _n_potentials;

  std::vector<const VariableValue *> _el;

  const ChemicalCompositionAction & _action;
  std::vector<unsigned int> _el_ids;

  // Re-initialization data
  const enum class ReinitializationType { NONE, TIME, LAST_DOF, CACHE } _reinit;

  /// Mass unit for output species
  const enum class OutputMassUnit { MOLES, FRACTION } _output_mass_unit;

  const std::vector<std::string> & _ph_names;
  const std::vector<std::string> & _element_potentials;
  const std::vector<std::pair<std::string, std::string>> & _species_phase_pairs;
  const std::vector<std::pair<std::string, std::string>> & _vapor_phase_pairs;
  const std::vector<std::pair<std::string, std::string>> & _phase_element_pairs;

  /// DOF data (Used only for reinitialization)
  std::unordered_map<dof_id_type, Thermochimica::ReinitializationData> _data;

  ///@{ Element chemical potential output
  const bool _output_element_potentials;
  const bool _output_vapor_pressures;
  const bool _output_element_phases;
  ///@}

  /// Writable phase amount variables
  std::vector<MooseWritableVariable *> _ph;

  /// Writable species amount variables
  std::vector<MooseWritableVariable *> _sp;

  /// Writable vapour pressures for each element
  std::vector<MooseWritableVariable *> _vp;

  /// Writable chemical potential variables for each element
  std::vector<MooseWritableVariable *> _el_pot;

  /// Writable variable for molar amounts of each element in specified phase
  std::vector<MooseWritableVariable *> _el_ph;

  /// Communication socket
  int _socket;

  /// Child PID
  pid_t _pid;

  /// Shared memory pointer for dof_id_type values
  dof_id_type * _shared_dofid_mem;

  /// Shared memory pointer for Real values
  Real * _shared_real_mem;

  // Current node or element ID
  dof_id_type _current_id;

  // Kd-Tree cache
  // ValueCache<Thermochimica::ReinitializationData> _thermo_cache;

  // Helper variables for KD-Tree cache
  // Total moles of elements in the system
  Real _moles_elements;
  // ValueCache key {T, P, {C_normalized}} (k = _n_elements + 2)
  std::vector<Real> _current_state_space;

  using ThermochimicaDataBaseParent<is_nodal>::isCoupled;
  using ThermochimicaDataBaseParent<is_nodal>::isParamValid;
  using ThermochimicaDataBaseParent<is_nodal>::coupledValue;
  using ThermochimicaDataBaseParent<is_nodal>::coupledComponents;
  using ThermochimicaDataBaseParent<is_nodal>::writableVariable;
};

typedef ThermochimicaDataBase<true> ThermochimicaNodalData;
typedef ThermochimicaDataBase<false> ThermochimicaElementData;
