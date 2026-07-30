//* This file is part of the MOOSE framework
//* https://mooseframework.inl.gov
//*
//* All rights reserved, see COPYRIGHT for full restrictions
//* https://github.com/idaholab/moose/blob/master/COPYRIGHT
//*
//* Licensed under LGPL 2.1, please see LICENSE for details
//* https://www.gnu.org/licenses/lgpl-2.1.html

#pragma once

#include "ThreadedGeneralUserObject.h"
#include "BlockRestrictable.h"
#include "ThermochimicaConfiguration.h"
#include "ValueCache.h"
#include "libmesh/dof_object.h"

#include <memory>
#include <limits>
#include <optional>
#include <unordered_map>
#include <sys/types.h>

#ifdef MOOSE_LIBTORCH_ENABLED
#include <torch/script.h>
#endif

#ifdef THERMOCHIMICA_ENABLED
#include "Thermochimica-cxx.h"
#endif

template <typename OutputType>
class MooseVariableField;
namespace libMesh
{
class Node;
class Elem;
}

/**
 * Executes Thermochimica equilibrium calculations in exact or adaptive batches.
 *
 * Each threaded copy owns an isolated worker process because Thermochimica stores its state in
 * Fortran modules. The action is the only supported way to construct this object.
 */
class ThermochimicaData : public ThreadedGeneralUserObject, public BlockRestrictable
{
public:
  static InputParameters validParams();
  ThermochimicaData(const InputParameters & parameters);
  ~ThermochimicaData() override;

  void initialize() override;
  void execute() override;
  void threadJoin(const UserObject & other) override;
  void finalize() override;

protected:
  struct InputSource
  {
    MooseVariableField<Real> * variable = nullptr;
    Real constant = 0;
  };

  struct SharedHeader
  {
    unsigned int command = 0;
    unsigned int count = 0;
    unsigned int warm_starts = 0;
    unsigned int exact_solves = 0;
    unsigned int gem_iterations = 0;
    unsigned int exact_reuse_hits = 0;
    unsigned int surrogate_hits = 0;
    unsigned int phase_rejections = 0;
    unsigned int geometry_rejections = 0;
    unsigned int error_rejections = 0;
    unsigned int invariant_rejections = 0;
    unsigned int invalid_state_rejections = 0;
    unsigned int audits = 0;
    unsigned int audit_failures = 0;
    unsigned int nearest_warm_starts = 0;
    unsigned int cold_retries = 0;
    unsigned int cache_entries = 0;
    unsigned int cache_saturated = 0;
    unsigned int sensitivity_successes = 0;
    unsigned int sensitivity_failures = 0;
    unsigned int sensitivity_condition_rejections = 0;
    unsigned int sensitivity_residual_rejections = 0;
    unsigned int unsupported_model_rejections = 0;
    unsigned int state_restore_failures = 0;
    unsigned int complementarity_rejections = 0;
    unsigned int linear_retrieves = 0;
    unsigned int ellipsoid_growths = 0;
    unsigned int ellipsoid_shrinks = 0;
    unsigned int neural_batches = 0;
    unsigned int neural_out_of_bounds = 0;
    unsigned int neural_support_rejections = 0;
    unsigned int neural_phase_rejections = 0;
    unsigned int neural_disabled = 0;
    std::size_t sensitivity_bytes = 0;
    int worker_status = 0;
    Real solve_seconds = 0;
    Real sensitivity_seconds = 0;
    Real neural_inference_seconds = 0;
    char worker_error[512] = {};
  };

  enum class Command : unsigned int
  {
    SOLVE = 1,
    STOP = 2
  };

  void createWorker();
  void destroyWorker();
  [[noreturn]] void workerLoop();
  void initializeThermochimica();
  int solveRow(unsigned int row, bool allow_prediction = true);
#ifdef MOOSE_LIBTORCH_ENABLED
  void initializeNeuralSurrogate();
  void evaluateNeuralBatch();
#endif
#ifdef THERMOCHIMICA_ENABLED
  struct CacheRecord
  {
    std::vector<Real> coordinates;
    std::vector<Real> outputs;
    std::vector<int> phase_signature;
    std::vector<int> active_species_signature;
    std::vector<int> assemblage_token;
    Real total_scale = 1.0;
    std::optional<Thermochimica::ReinitializationData> reinit;
    std::vector<Real> output_jacobian;
    std::vector<Real> metric;
    std::vector<Real> state_log_amounts;
    std::vector<Real> state_jacobian;
    Real sensitivity_rcond = 0.0;
    bool sensitivity_available = false;
  };

  struct OutputEvaluationContext
  {
    bool use_indexed_outputs;
    const std::vector<double> & moles_phase;
    Real phase_total;
    Real pressure;
    std::unordered_map<int, std::pair<Real, int>> element_totals;
  };

  int evaluateOutput(const ThermochimicaConfiguration::PhaseOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::SpeciesOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::ElementPotentialOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::VaporPressureOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::ElementDistributionOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::ChemicalPotentialOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::PhaseGibbsEnergyOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::PhaseDrivingForceOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::SystemGibbsEnergyOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::SystemPropertyOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  int evaluateOutput(const ThermochimicaConfiguration::ConstituentFractionOutput & output,
                     OutputEvaluationContext & context,
                     Real & value) const;
  bool loadPreviousState(dof_id_type id);
  void storePreviousState(dof_id_type id);
  bool normalizedInput(unsigned int row, std::vector<Real> & key, Real & total_scale) const;
  bool predictRow(unsigned int row, const std::vector<Real> & key, Real total_scale, bool & audit);
  bool
  predictKktRow(unsigned int row, const std::vector<Real> & key, Real total_scale, bool & audit);
  int evaluateCurrentOutputs(unsigned int row, Real * result) const;
  bool buildKktSensitivity(CacheRecord & record, unsigned int row, const std::vector<Real> & key);
  bool updateKktEllipsoid(const std::vector<Real> & key,
                          Real total_scale,
                          const std::vector<int> & phase_signature,
                          const Real * exact_outputs);
  void shrinkAuditedEllipsoid(const std::vector<Real> & key);
  std::vector<Real> physicalInputDirection(const std::vector<Real> & internal_inputs,
                                           unsigned int coordinate) const;
  void cacheExactRow(unsigned int row,
                     const std::vector<Real> & key,
                     Real total_scale,
                     const std::vector<int> & phase_signature,
                     const Thermochimica::ReinitializationData * reinit);
  bool loadNearestState(const std::vector<Real> & key, Real total_scale);
  bool outputsWithinTolerance(const std::vector<Real> & expected, const Real * actual) const;
#endif
  void flushBatch(unsigned int count);
  void publishRow(unsigned int row);

  InputSource inputSource(const std::string & value);
  Real
  inputValue(const InputSource & source, bool nodal, const libMesh::Elem * elem = nullptr) const;
  bool ownsEntity(dof_id_type id) const;
  bool includesNode(const libMesh::Node & node) const;
  bool includesElement(const libMesh::Elem & elem) const;

  void writeMessage(char message);
  char readMessage();

  const ThermochimicaConfigurationPtr _configuration;
  const bool _nodal;
  const unsigned int _thread_count;

  InputSource _temperature;
  InputSource _pressure;
  std::vector<MooseVariableField<Real> *> _elements;
  std::vector<MooseVariableField<Real> *> _outputs;

  int _socket = -1;
  pid_t _worker_pid = -1;
  void * _shared_memory = nullptr;
  std::size_t _shared_memory_size = 0;
  SharedHeader * _header = nullptr;
  dof_id_type * _entity_ids = nullptr;
  int * _row_status = nullptr;
  Real * _inputs = nullptr;
  Real * _results = nullptr;

  dof_id_type _current_entity = libMesh::DofObject::invalid_id;
  unsigned long _evaluated_states = 0;
  unsigned long _batches = 0;
  unsigned long _warm_starts = 0;
  unsigned long _exact_solves = 0;
  unsigned long _gem_iterations = 0;
  unsigned long _exact_reuse_hits = 0;
  unsigned long _surrogate_hits = 0;
  unsigned long _phase_rejections = 0;
  unsigned long _geometry_rejections = 0;
  unsigned long _error_rejections = 0;
  unsigned long _invariant_rejections = 0;
  unsigned long _invalid_state_rejections = 0;
  unsigned long _audits = 0;
  unsigned long _audit_failures = 0;
  unsigned long _nearest_warm_starts = 0;
  unsigned long _cold_retries = 0;
  unsigned long _cache_entries = 0;
  unsigned long _sensitivity_successes = 0;
  unsigned long _sensitivity_failures = 0;
  unsigned long _sensitivity_condition_rejections = 0;
  unsigned long _sensitivity_residual_rejections = 0;
  unsigned long _unsupported_model_rejections = 0;
  unsigned long _state_restore_failures = 0;
  unsigned long _complementarity_rejections = 0;
  unsigned long _linear_retrieves = 0;
  unsigned long _ellipsoid_growths = 0;
  unsigned long _ellipsoid_shrinks = 0;
  unsigned long _neural_batches = 0;
  unsigned long _neural_out_of_bounds = 0;
  unsigned long _neural_support_rejections = 0;
  unsigned long _neural_phase_rejections = 0;
  unsigned long _neural_disabled_workers = 0;
  std::size_t _sensitivity_bytes = 0;
  bool _cache_saturated = false;
  Real _solve_seconds = 0;
  Real _sensitivity_seconds = 0;
  Real _neural_inference_seconds = 0;
  Real _packing_seconds = 0;
  Real _ipc_seconds = 0;

#ifdef THERMOCHIMICA_ENABLED
  int _reinit_elements = 0;
  int _reinit_species = 0;
  std::unordered_map<dof_id_type, std::size_t> _previous_state_slots;
  std::vector<int> _previous_state_integers;
  std::vector<Real> _previous_state_reals;
  std::vector<unsigned char> _previous_state_available;
  std::unique_ptr<ValueCache<std::size_t>> _cache;
  std::vector<CacheRecord> _cache_records;
  unsigned long _worker_accepted_predictions = 0;
  std::size_t _worker_sensitivity_bytes = 0;
  std::vector<Real> _audit_prediction;
  std::size_t _audit_record = std::numeric_limits<std::size_t>::max();
#endif
  bool _worker_has_previous_solve = false;
#ifdef MOOSE_LIBTORCH_ENABLED
  struct NeuralPhaseGate
  {
    std::size_t output_index;
    std::size_t logit_index;
    Real presence_threshold;
  };

  struct NeuralInvariantGroup
  {
    std::vector<std::size_t> output_indices;
    Real target;
    Real tolerance;
  };

  struct NeuralSupportGate
  {
    std::vector<unsigned char> signature;
    std::size_t distance_index;
    Real radius;
  };

  std::unique_ptr<torch::jit::script::Module> _neural_model;
  std::vector<Real> _neural_lower_bounds;
  std::vector<Real> _neural_upper_bounds;
  std::vector<NeuralPhaseGate> _neural_phase_gates;
  std::vector<NeuralInvariantGroup> _neural_invariant_groups;
  std::vector<NeuralSupportGate> _neural_support_gates;
  std::size_t _neural_model_output_width = 0;
  Real _neural_phase_confidence = 0.0;
  bool _neural_disabled = false;
#endif
};
