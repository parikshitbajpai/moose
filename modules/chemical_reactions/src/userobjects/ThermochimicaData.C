//* This file is part of the MOOSE framework
//* https://mooseframework.inl.gov
//*
//* All rights reserved, see COPYRIGHT for full restrictions
//* https://github.com/idaholab/moose/blob/master/COPYRIGHT
//*
//* Licensed under LGPL 2.1, please see LICENSE for details
//* https://www.gnu.org/licenses/lgpl-2.1.html

#include "ThermochimicaData.h"
#include "ThermochimicaUtils.h"
#include "MooseVariable.h"
#include "MooseVariableField.h"
#include "MooseVariableFE.h"
#include "MooseVariableFV.h"
#include "MooseMesh.h"
#include "MooseUtils.h"
#include "FEProblemBase.h"
#include "AuxiliarySystem.h"
#include "libmesh/elem.h"
#include "libmesh/node.h"
#include "libmesh/threads.h"

#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <new>
#include <numeric>
#include <optional>
#include <sstream>
#include <type_traits>

#ifdef MOOSE_LIBTORCH_ENABLED
#include "nlohmann/json.h"
#endif

#ifdef THERMOCHIMICA_ENABLED
#include "Thermochimica-cxx.h"
#include "checkUnits.h"
#endif

registerMooseObject("ChemicalReactionsApp", ThermochimicaData);

namespace
{
Threads::spin_mutex output_mutex;
Threads::spin_mutex input_mutex;

template <typename Output>
std::string
outputVariable(const Output & output)
{
  return output.variable;
}

#ifdef MOOSE_LIBTORCH_ENABLED
std::string
sha256File(const std::string & filename)
{
  std::ifstream stream(filename, std::ios::binary);
  if (!stream)
    throw std::runtime_error("unable to open database for hashing");
  std::vector<std::uint8_t> message((std::istreambuf_iterator<char>(stream)),
                                    std::istreambuf_iterator<char>());
  const std::uint64_t bit_size = static_cast<std::uint64_t>(message.size()) * 8;
  message.push_back(0x80);
  while (message.size() % 64 != 56)
    message.push_back(0);
  for (const auto shift : {56, 48, 40, 32, 24, 16, 8, 0})
    message.push_back(static_cast<std::uint8_t>(bit_size >> shift));

  constexpr std::array<std::uint32_t, 64> constants = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
      0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
      0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
      0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
      0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
      0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
      0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
      0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
      0xc67178f2};
  std::array<std::uint32_t, 8> hash = {
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
      0x5be0cd19};
  auto rotate = [](const std::uint32_t value, const unsigned int count)
  { return (value >> count) | (value << (32 - count)); };

  for (std::size_t offset = 0; offset < message.size(); offset += 64)
  {
    std::array<std::uint32_t, 64> words = {};
    for (const auto i : make_range(16))
      words[i] = (std::uint32_t(message[offset + 4 * i]) << 24) |
                 (std::uint32_t(message[offset + 4 * i + 1]) << 16) |
                 (std::uint32_t(message[offset + 4 * i + 2]) << 8) |
                 std::uint32_t(message[offset + 4 * i + 3]);
    for (const auto i : make_range(16, 64))
    {
      const auto first =
          rotate(words[i - 15], 7) ^ rotate(words[i - 15], 18) ^ (words[i - 15] >> 3);
      const auto second =
          rotate(words[i - 2], 17) ^ rotate(words[i - 2], 19) ^ (words[i - 2] >> 10);
      words[i] = words[i - 16] + first + words[i - 7] + second;
    }

    auto state = hash;
    for (const auto i : make_range(64))
    {
      const auto sum1 =
          rotate(state[4], 6) ^ rotate(state[4], 11) ^ rotate(state[4], 25);
      const auto choice = (state[4] & state[5]) ^ (~state[4] & state[6]);
      const auto temporary1 = state[7] + sum1 + choice + constants[i] + words[i];
      const auto sum0 =
          rotate(state[0], 2) ^ rotate(state[0], 13) ^ rotate(state[0], 22);
      const auto majority =
          (state[0] & state[1]) ^ (state[0] & state[2]) ^ (state[1] & state[2]);
      const auto temporary2 = sum0 + majority;
      for (const auto reverse : make_range(7))
      {
        const auto j = 7 - reverse;
        state[j] = state[j - 1];
      }
      state[4] += temporary1;
      state[0] = temporary1 + temporary2;
    }
    for (const auto i : make_range(8))
      hash[i] += state[i];
  }

  std::ostringstream result;
  result << std::hex << std::setfill('0');
  for (const auto value : hash)
    result << std::setw(8) << value;
  return result.str();
}
#endif

std::size_t
alignedOffset(const std::size_t offset, const std::size_t alignment)
{
  return (offset + alignment - 1) & ~(alignment - 1);
}

#ifdef THERMOCHIMICA_ENABLED
int
currentPhaseIndex(const std::string & phase)
{
  const auto phases = Thermochimica::getPhaseNamesSystem();
  const auto found = std::find(phases.begin(), phases.end(), phase);
  return found == phases.end() ? -1 : static_cast<int>(std::distance(phases.begin(), found));
}

int
currentComponentIndex(const int phase_index,
                      const std::string & component,
                      const ThermochimicaConfiguration::ChemicalPotentialKind kind)
{
  const auto components = kind == ThermochimicaConfiguration::ChemicalPotentialKind::ENDMEMBER
                              ? Thermochimica::getSpeciesInPhase(phase_index)
                              : Thermochimica::getThermodynamicSpeciesInPhase(phase_index);
  const auto found = std::find(components.begin(), components.end(), component);
  return found == components.end() ? -1
                                   : static_cast<int>(std::distance(components.begin(), found));
}
#endif
}

InputParameters
ThermochimicaData::validParams()
{
  InputParameters params = ThreadedGeneralUserObject::validParams();
  params += BlockRestrictable::validParams();
  ThermochimicaUtils::addClassDescription(
      params,
      "Internal batched Thermochimica equilibrium executor with optional adaptive "
      "acceleration.");
  params.addPrivateParam<ThermochimicaConfigurationPtr>("_configuration");
  params.addCoupledVar("temperature", "Temperature input used to establish execution dependencies");
  params.addCoupledVar("pressure", 1.0, "Pressure input used to establish execution dependencies");
  params.addCoupledVar("elements", "Element inputs used to establish execution dependencies");
  return params;
}

ThermochimicaData::ThermochimicaData(const InputParameters & parameters)
  : ThreadedGeneralUserObject(parameters),
    BlockRestrictable(this),
    _configuration(parameters.get<ThermochimicaConfigurationPtr>("_configuration")),
    _nodal(_configuration->location == ThermochimicaConfiguration::EvaluationLocation::NODAL),
    _thread_count(libMesh::n_threads()),
    _temperature(inputSource(_configuration->temperature)),
    _pressure(inputSource(_configuration->pressure))
{
  ThermochimicaUtils::checkLibraryAvailability(*this);

  _elements.reserve(_configuration->element_variables.size());
  for (const auto & name : _configuration->element_variables)
    _elements.push_back(
        &dynamic_cast<MooseVariableField<Real> &>(_subproblem.getActualFieldVariable(_tid, name)));

  _outputs.reserve(_configuration->outputs.size());
  for (const auto & output : _configuration->outputs)
    std::visit(
        [&](const auto & descriptor)
        {
          _outputs.push_back(&dynamic_cast<MooseVariableField<Real> &>(
              _subproblem.getActualFieldVariable(_tid, descriptor.variable)));
        },
        output);

  createWorker();
}

ThermochimicaData::~ThermochimicaData() { destroyWorker(); }

void
ThermochimicaData::initialize()
{
  _evaluated_states = 0;
  _batches = 0;
  _warm_starts = 0;
  _exact_solves = 0;
  _gem_iterations = 0;
  _exact_reuse_hits = 0;
  _surrogate_hits = 0;
  _phase_rejections = 0;
  _geometry_rejections = 0;
  _error_rejections = 0;
  _invariant_rejections = 0;
  _invalid_state_rejections = 0;
  _audits = 0;
  _audit_failures = 0;
  _nearest_warm_starts = 0;
  _cold_retries = 0;
  _cache_entries = 0;
  _sensitivity_successes = 0;
  _sensitivity_failures = 0;
  _sensitivity_condition_rejections = 0;
  _sensitivity_residual_rejections = 0;
  _unsupported_model_rejections = 0;
  _state_restore_failures = 0;
  _complementarity_rejections = 0;
  _linear_retrieves = 0;
  _ellipsoid_growths = 0;
  _ellipsoid_shrinks = 0;
  _neural_batches = 0;
  _neural_out_of_bounds = 0;
  _neural_disabled_workers = 0;
  _cache_saturated = false;
  _solve_seconds = 0;
  _sensitivity_seconds = 0;
  _neural_inference_seconds = 0;
  _packing_seconds = 0;
  _ipc_seconds = 0;
}

ThermochimicaData::InputSource
ThermochimicaData::inputSource(const std::string & value)
{
  InputSource source;
  if (_subproblem.hasVariable(value))
    source.variable =
        &dynamic_cast<MooseVariableField<Real> &>(_subproblem.getActualFieldVariable(_tid, value));
  else
  {
    try
    {
      source.constant = MooseUtils::convert<Real>(value);
    }
    catch (...)
    {
      mooseError("Thermochimica input '", value, "' is neither a field variable nor a number.");
    }
  }
  return source;
}

Real
ThermochimicaData::inputValue(const InputSource & source,
                              const bool nodal,
                              const libMesh::Elem * elem) const
{
  if (!source.variable)
    return source.constant;
  if (nodal)
  {
    const auto * variable = dynamic_cast<const MooseVariable *>(source.variable);
    if (!variable)
      mooseError("Nodal Thermochimica inputs must be nodal finite-element variables.");
    return variable->nodalValue();
  }
  if (!elem)
    mooseError("An element is required to evaluate an elemental Thermochimica input.");
  if (const auto * variable = dynamic_cast<const MooseVariableFE<Real> *>(source.variable))
    return variable->getElementalValue(elem);
  if (const auto * variable = dynamic_cast<const MooseVariableFV<Real> *>(source.variable))
    return variable->getElementalValue(elem);
  mooseError("Elemental Thermochimica inputs must be finite-element or finite-volume variables.");
}

bool
ThermochimicaData::ownsEntity(const dof_id_type id) const
{
  return id % _thread_count == _tid;
}

bool
ThermochimicaData::includesElement(const libMesh::Elem & elem) const
{
  return hasBlocks(elem.subdomain_id());
}

bool
ThermochimicaData::includesNode(const libMesh::Node & node) const
{
  const auto & node_blocks = _fe_problem.mesh().getNodeBlockIds(node);
  return std::any_of(
      node_blocks.begin(), node_blocks.end(), [this](const auto id) { return hasBlocks(id); });
}

void
ThermochimicaData::execute()
{
  unsigned int row = 0;
  auto store_inputs = [&](const auto & entity)
  {
    const auto packing_start = std::chrono::steady_clock::now();
    const auto id = entity.id();
    _entity_ids[row] = id;
    auto * input = _inputs + row * _configuration->inputWidth();
    const libMesh::Elem * elem = nullptr;
    if constexpr (std::is_same_v<std::decay_t<decltype(entity)>, libMesh::Elem>)
      elem = &entity;
    {
      Threads::spin_mutex::scoped_lock lock(input_mutex);
      if constexpr (!std::is_same_v<std::decay_t<decltype(entity)>, libMesh::Elem>)
        _fe_problem.reinitNode(&entity, _tid);
      input[0] = inputValue(_temperature, _nodal, elem);
      input[1] = inputValue(_pressure, _nodal, elem);
      for (const auto i : index_range(_elements))
        input[2 + i] = inputValue({_elements[i], 0}, _nodal, elem);
    }
    _packing_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - packing_start).count();

    ++row;
    if (row == _configuration->batch_size)
    {
      flushBatch(row);
      row = 0;
    }
  };

  if (_nodal)
  {
    auto & mesh = _fe_problem.mesh().getMesh();
    for (auto it = mesh.local_nodes_begin(); it != mesh.local_nodes_end(); ++it)
    {
      const auto & node = **it;
      if (!ownsEntity(node.id()) || !includesNode(node))
        continue;
      store_inputs(node);
    }
  }
  else
  {
    auto & mesh = _fe_problem.mesh().getMesh();
    for (auto it = mesh.active_local_elements_begin(); it != mesh.active_local_elements_end(); ++it)
    {
      const auto & elem = **it;
      if (!ownsEntity(elem.id()) || !includesElement(elem))
        continue;
      store_inputs(elem);
    }
  }

  if (row)
    flushBatch(row);
}

void
ThermochimicaData::threadJoin(const UserObject & other)
{
  const auto & data = static_cast<const ThermochimicaData &>(other);
  _evaluated_states += data._evaluated_states;
  _batches += data._batches;
  _warm_starts += data._warm_starts;
  _exact_solves += data._exact_solves;
  _gem_iterations += data._gem_iterations;
  _exact_reuse_hits += data._exact_reuse_hits;
  _surrogate_hits += data._surrogate_hits;
  _phase_rejections += data._phase_rejections;
  _geometry_rejections += data._geometry_rejections;
  _error_rejections += data._error_rejections;
  _invariant_rejections += data._invariant_rejections;
  _invalid_state_rejections += data._invalid_state_rejections;
  _audits += data._audits;
  _audit_failures += data._audit_failures;
  _nearest_warm_starts += data._nearest_warm_starts;
  _cold_retries += data._cold_retries;
  _cache_entries += data._cache_entries;
  _sensitivity_successes += data._sensitivity_successes;
  _sensitivity_failures += data._sensitivity_failures;
  _sensitivity_condition_rejections += data._sensitivity_condition_rejections;
  _sensitivity_residual_rejections += data._sensitivity_residual_rejections;
  _unsupported_model_rejections += data._unsupported_model_rejections;
  _state_restore_failures += data._state_restore_failures;
  _complementarity_rejections += data._complementarity_rejections;
  _linear_retrieves += data._linear_retrieves;
  _ellipsoid_growths += data._ellipsoid_growths;
  _ellipsoid_shrinks += data._ellipsoid_shrinks;
  _neural_batches += data._neural_batches;
  _neural_out_of_bounds += data._neural_out_of_bounds;
  _neural_disabled_workers += data._neural_disabled_workers;
  _sensitivity_bytes += data._sensitivity_bytes;
  _cache_saturated = _cache_saturated || data._cache_saturated;
  _solve_seconds += data._solve_seconds;
  _sensitivity_seconds += data._sensitivity_seconds;
  _neural_inference_seconds += data._neural_inference_seconds;
  _packing_seconds += data._packing_seconds;
  _ipc_seconds += data._ipc_seconds;
}

void
ThermochimicaData::finalize()
{
  if (!_outputs.empty())
  {
    auto & auxiliary = _fe_problem.getAuxiliarySystem();
    auxiliary.solution().close();
    auxiliary.update();
  }
  if (_configuration->report_performance)
    _console << "ThermochimicaData '" << name() << "': states=" << _evaluated_states
             << ", batches=" << _batches << ", exact_solves=" << _exact_solves
             << ", gem_iterations=" << _gem_iterations << ", warm_starts=" << _warm_starts
             << ", exact_reuse_hits=" << _exact_reuse_hits << ", surrogate_hits=" << _surrogate_hits
             << ", rejections=(phase:" << _phase_rejections << ",geometry:" << _geometry_rejections
             << ",error:" << _error_rejections << ",invariant:" << _invariant_rejections
             << ",invalid_state:" << _invalid_state_rejections << "), audits=" << _audits
             << ", audit_failures=" << _audit_failures
             << ", nearest_warm_starts=" << _nearest_warm_starts
             << ", cold_retries=" << _cold_retries << ", cache_entries=" << _cache_entries
             << ", cache_saturated=" << (_cache_saturated ? 1 : 0)
             << ", sensitivity_successes=" << _sensitivity_successes
             << ", sensitivity_failures=" << _sensitivity_failures
             << ", sensitivity_condition_rejections=" << _sensitivity_condition_rejections
             << ", sensitivity_residual_rejections=" << _sensitivity_residual_rejections
             << ", unsupported_model_rejections=" << _unsupported_model_rejections
             << ", state_restore_failures=" << _state_restore_failures
             << ", complementarity_rejections=" << _complementarity_rejections
             << ", linear_retrieves=" << _linear_retrieves
             << ", ellipsoid_growths=" << _ellipsoid_growths
             << ", ellipsoid_shrinks=" << _ellipsoid_shrinks
             << ", neural_batches=" << _neural_batches
             << ", neural_out_of_bounds=" << _neural_out_of_bounds
             << ", neural_disabled_workers=" << _neural_disabled_workers
             << ", neural_inference_time=" << _neural_inference_seconds << " s"
             << ", sensitivity_bytes=" << _sensitivity_bytes
             << ", sensitivity_time=" << _sensitivity_seconds << " s"
             << ", worker_solve_time=" << _solve_seconds << " s, packing_time=" << _packing_seconds
             << " s, ipc_time=" << _ipc_seconds << " s" << std::endl;
}

void
ThermochimicaData::createWorker()
{
  std::size_t offset = sizeof(SharedHeader);
  offset = alignedOffset(offset, alignof(dof_id_type));
  const auto ids_offset = offset;
  offset += _configuration->batch_size * sizeof(dof_id_type);
  offset = alignedOffset(offset, alignof(int));
  const auto status_offset = offset;
  offset += _configuration->batch_size * sizeof(int);
  offset = alignedOffset(offset, alignof(Real));
  const auto inputs_offset = offset;
  offset += _configuration->batch_size * _configuration->inputWidth() * sizeof(Real);
  const auto results_offset = offset;
  offset += _configuration->batch_size * _configuration->outputWidth() * sizeof(Real);
  _shared_memory_size = offset;

  _shared_memory =
      mmap(nullptr, _shared_memory_size, PROT_READ | PROT_WRITE, MAP_ANONYMOUS | MAP_SHARED, -1, 0);
  if (_shared_memory == MAP_FAILED)
    mooseError("Failed to allocate shared memory for the Thermochimica worker: ", strerror(errno));

  auto * bytes = static_cast<std::byte *>(_shared_memory);
  _header = reinterpret_cast<SharedHeader *>(bytes);
  new (_header) SharedHeader();
  _entity_ids = reinterpret_cast<dof_id_type *>(bytes + ids_offset);
  _row_status = reinterpret_cast<int *>(bytes + status_offset);
  _inputs = reinterpret_cast<Real *>(bytes + inputs_offset);
  _results = reinterpret_cast<Real *>(bytes + results_offset);

  int sockets[2];
  if (socketpair(AF_UNIX, SOCK_STREAM, 0, sockets) != 0)
  {
    const auto socket_errno = errno;
    munmap(_shared_memory, _shared_memory_size);
    _shared_memory = nullptr;
    errno = socket_errno;
    mooseError("Failed to create a socket for the Thermochimica worker: ", strerror(errno));
  }

  _worker_pid = fork();
  if (_worker_pid < 0)
  {
    const auto fork_errno = errno;
    close(sockets[0]);
    close(sockets[1]);
    munmap(_shared_memory, _shared_memory_size);
    _shared_memory = nullptr;
    errno = fork_errno;
    mooseError("Failed to fork the Thermochimica worker: ", strerror(errno));
  }
  if (_worker_pid == 0)
  {
    close(sockets[1]);
    _socket = sockets[0];
    workerLoop();
  }

  close(sockets[0]);
  _socket = sockets[1];
  try
  {
    if (readMessage() != 'I')
      mooseError("Thermochimica worker failed during initialization.");
    if (_header->worker_status)
      mooseError("Thermochimica worker initialization failed with status ",
                 _header->worker_status,
                 _header->worker_error[0] ? ": " : ".",
                 _header->worker_error);
  }
  catch (...)
  {
    destroyWorker();
    throw;
  }
}

void
ThermochimicaData::destroyWorker()
{
  if (_worker_pid > 0)
  {
    _header->command = static_cast<unsigned int>(Command::STOP);
    try
    {
      writeMessage('Q');
      readMessage();
    }
    catch (...)
    {
    }
    if (_socket >= 0)
    {
      close(_socket);
      _socket = -1;
    }
    int status = 0;
    while (waitpid(_worker_pid, &status, 0) < 0 && errno == EINTR)
      ;
    _worker_pid = -1;
  }
  if (_socket >= 0)
  {
    close(_socket);
    _socket = -1;
  }
  if (_shared_memory && _shared_memory != MAP_FAILED)
  {
    munmap(_shared_memory, _shared_memory_size);
    _shared_memory = nullptr;
  }
}

void
ThermochimicaData::writeMessage(const char message)
{
  ssize_t written;
  do
    written = send(_socket, &message, sizeof(message), MSG_NOSIGNAL);
  while (written < 0 && errno == EINTR);
  if (written != sizeof(message))
    mooseError("Thermochimica worker communication failed while writing: ", strerror(errno));
}

char
ThermochimicaData::readMessage()
{
  char message = 0;
  ssize_t received;
  do
    received = recv(_socket, &message, sizeof(message), 0);
  while (received < 0 && errno == EINTR);
  if (received == 0)
    mooseError("Thermochimica worker exited unexpectedly.");
  if (received != sizeof(message))
    mooseError("Thermochimica worker communication failed while reading: ", strerror(errno));
  return message;
}

void
ThermochimicaData::flushBatch(const unsigned int count)
{
  _header->command = static_cast<unsigned int>(Command::SOLVE);
  _header->count = count;
  _header->worker_status = 0;
  _header->warm_starts = 0;
  _header->exact_solves = 0;
  _header->gem_iterations = 0;
  _header->exact_reuse_hits = 0;
  _header->surrogate_hits = 0;
  _header->phase_rejections = 0;
  _header->geometry_rejections = 0;
  _header->error_rejections = 0;
  _header->invariant_rejections = 0;
  _header->invalid_state_rejections = 0;
  _header->audits = 0;
  _header->audit_failures = 0;
  _header->nearest_warm_starts = 0;
  _header->cold_retries = 0;
  _header->cache_entries = 0;
  _header->cache_saturated = 0;
  _header->sensitivity_successes = 0;
  _header->sensitivity_failures = 0;
  _header->sensitivity_condition_rejections = 0;
  _header->sensitivity_residual_rejections = 0;
  _header->unsupported_model_rejections = 0;
  _header->state_restore_failures = 0;
  _header->complementarity_rejections = 0;
  _header->linear_retrieves = 0;
  _header->ellipsoid_growths = 0;
  _header->ellipsoid_shrinks = 0;
  _header->neural_batches = 0;
  _header->neural_out_of_bounds = 0;
  _header->neural_disabled = 0;
  _header->sensitivity_bytes = 0;
  _header->solve_seconds = 0;
  _header->sensitivity_seconds = 0;
  _header->neural_inference_seconds = 0;
  const auto ipc_start = std::chrono::steady_clock::now();
  writeMessage('Q');
  if (readMessage() != 'R')
    mooseError("Thermochimica worker returned an invalid response.");
  const auto round_trip_seconds =
      std::chrono::duration<Real>(std::chrono::steady_clock::now() - ipc_start).count();
  if (_header->worker_status)
    mooseError("Thermochimica worker failed with status ", _header->worker_status, ".");
  if (_header->audit_failures && _header->worker_error[0])
    mooseWarning(_header->worker_error);

  for (const auto row : make_range(count))
  {
    if (_row_status[row])
      mooseError("Thermochimica failed for entity ",
                 _entity_ids[row],
                 " with status ",
                 _row_status[row],
                 ".");
    publishRow(row);
  }

  _evaluated_states += count;
  ++_batches;
  _warm_starts += _header->warm_starts;
  _exact_solves += _header->exact_solves;
  _gem_iterations += _header->gem_iterations;
  _exact_reuse_hits += _header->exact_reuse_hits;
  _surrogate_hits += _header->surrogate_hits;
  _phase_rejections += _header->phase_rejections;
  _geometry_rejections += _header->geometry_rejections;
  _error_rejections += _header->error_rejections;
  _invariant_rejections += _header->invariant_rejections;
  _invalid_state_rejections += _header->invalid_state_rejections;
  _audits += _header->audits;
  _audit_failures += _header->audit_failures;
  _nearest_warm_starts += _header->nearest_warm_starts;
  _cold_retries += _header->cold_retries;
  _cache_entries = _header->cache_entries;
  _sensitivity_successes += _header->sensitivity_successes;
  _sensitivity_failures += _header->sensitivity_failures;
  _sensitivity_condition_rejections += _header->sensitivity_condition_rejections;
  _sensitivity_residual_rejections += _header->sensitivity_residual_rejections;
  _unsupported_model_rejections += _header->unsupported_model_rejections;
  _state_restore_failures += _header->state_restore_failures;
  _complementarity_rejections += _header->complementarity_rejections;
  _linear_retrieves += _header->linear_retrieves;
  _ellipsoid_growths += _header->ellipsoid_growths;
  _ellipsoid_shrinks += _header->ellipsoid_shrinks;
  _neural_batches += _header->neural_batches;
  _neural_out_of_bounds += _header->neural_out_of_bounds;
  _neural_disabled_workers += _header->neural_disabled;
  _sensitivity_bytes = _header->sensitivity_bytes;
  _cache_saturated = _cache_saturated || _header->cache_saturated;
  _solve_seconds += _header->solve_seconds;
  _sensitivity_seconds += _header->sensitivity_seconds;
  _neural_inference_seconds += _header->neural_inference_seconds;
  _ipc_seconds += std::max<Real>(0.0, round_trip_seconds - _header->solve_seconds);
}

void
ThermochimicaData::publishRow(const unsigned int row)
{
  if (_outputs.empty())
    return;

  const libMesh::DofObject * entity =
      _nodal ? static_cast<const libMesh::DofObject *>(
                   _fe_problem.mesh().getMesh().node_ptr(_entity_ids[row]))
             : static_cast<const libMesh::DofObject *>(
                   _fe_problem.mesh().getMesh().elem_ptr(_entity_ids[row]));
  if (!entity)
    mooseError("Unable to find Thermochimica output entity ", _entity_ids[row], ".");

  Threads::spin_mutex::scoped_lock lock(output_mutex);
  auto & solution = _fe_problem.getAuxiliarySystem().solution();
  const auto * result = _results + row * _configuration->outputWidth();
  for (const auto output : index_range(_outputs))
  {
    const auto dof =
        entity->dof_number(_outputs[output]->sys().number(), _outputs[output]->number(), 0);
    solution.set(dof, result[output]);
  }
}

void
ThermochimicaData::initializeThermochimica()
{
#ifdef THERMOCHIMICA_ENABLED
  Thermochimica::setThermoFilename(_configuration->database);
  Thermochimica::parseThermoFile();
  if (const auto info = Thermochimica::checkInfoThermo(); info != 0)
  {
    _header->worker_status = info;
    return;
  }
  Thermochimica::checkTemperature(_configuration->temperature_unit);
  Thermochimica::setUnitTemperature(_configuration->temperature_unit);
  if (const auto info = Thermochimica::checkInfoThermo(); info != 0)
  {
    _header->worker_status = info;
    return;
  }
  Thermochimica::checkPressure(_configuration->pressure_unit);
  Thermochimica::setUnitPressure(_configuration->pressure_unit);
  if (const auto info = Thermochimica::checkInfoThermo(); info != 0)
  {
    _header->worker_status = info;
    return;
  }
  Thermochimica::checkMass(_configuration->composition_unit);
  Thermochimica::setUnitMass(_configuration->composition_unit);
  if (const auto info = Thermochimica::checkInfoThermo(); info != 0)
  {
    _header->worker_status = info;
    return;
  }

  int selection_info = 0;
  if (_configuration->phase_selection == ThermochimicaConfiguration::PhaseSelection::INCLUDE)
    selection_info = Thermochimica::setIncludedPhases(_configuration->selected_phases);
  else
    selection_info = Thermochimica::setExcludedPhases(_configuration->selected_phases);
  if (selection_info != 0)
  {
    _header->worker_status = selection_info;
    return;
  }
  Thermochimica::setHeatCapacityEnthalpyEntropyRequested(_configuration->needs_system_properties);
#endif
}

#ifdef MOOSE_LIBTORCH_ENABLED
void
ThermochimicaData::initializeNeuralSurrogate()
{
  if (_configuration->surrogate_model != ThermochimicaConfiguration::SurrogateModel::NEURAL)
    return;

  auto fail = [this](const std::string & message)
  {
    _header->worker_status = EINVAL;
    std::strncpy(_header->worker_error, message.c_str(), sizeof(_header->worker_error) - 1);
  };

  try
  {
    torch::jit::ExtraFilesMap extra_files{{"metadata.json", ""}};
    auto module = torch::jit::load(
        std::string(_configuration->surrogate_archive), c10::Device(c10::kCPU), extra_files);
    module.eval();
    if (extra_files["metadata.json"].empty())
    {
      fail("neural surrogate archive does not contain metadata.json");
      return;
    }

    const auto metadata = nlohmann::json::parse(extra_files["metadata.json"]);
    if (metadata.value("schema_version", 0) != 1 ||
        metadata.value("archive_type", "") != "thermochimica_neural_torchscript")
    {
      fail("unsupported neural surrogate archive schema");
      return;
    }
    if (metadata.value("elements", std::vector<std::string>()) != _configuration->elements ||
        metadata.value("temperature_unit", "") != _configuration->temperature_unit ||
        metadata.value("pressure_unit", "") != _configuration->pressure_unit ||
        metadata.value("composition_unit", "") != _configuration->composition_unit)
    {
      fail("neural surrogate elements or units do not match the ChemicalComposition block");
      return;
    }
    if (metadata.value("database_sha256", "") !=
        sha256File(std::string(_configuration->database)))
    {
      fail("neural surrogate database SHA-256 does not match the configured database");
      return;
    }
    const auto selection = metadata.value(
        "phase_selection", nlohmann::json{{"mode", "none"}, {"phases", nlohmann::json::array()}});
    const std::string selection_mode =
        _configuration->phase_selection == ThermochimicaConfiguration::PhaseSelection::INCLUDE
            ? "include"
        : _configuration->phase_selection == ThermochimicaConfiguration::PhaseSelection::EXCLUDE
            ? "exclude"
            : "none";
    if (selection.value("mode", "") != selection_mode ||
        selection.value("phases", std::vector<std::string>()) != _configuration->selected_phases)
    {
      fail("neural surrogate phase selection does not match the ChemicalComposition block");
      return;
    }

    const auto & outputs = metadata.at("outputs");
    if (!outputs.is_array() || outputs.size() != _configuration->outputs.size())
    {
      fail("neural surrogate output count does not match the ChemicalComposition block");
      return;
    }
    for (const auto output : index_range(_configuration->outputs))
    {
      const auto & descriptor = _configuration->outputs[output];
      const auto variable =
          std::visit([](const auto & value) { return outputVariable(value); }, descriptor);
      const bool descriptor_matches = std::visit(
          [&archive_output = outputs[output]](const auto & value)
          {
            using Output = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<Output, ThermochimicaConfiguration::PhaseOutput>)
              return archive_output.value("type", "") == "phase" &&
                     archive_output.value("phase", "") == value.phase;
            else if constexpr (std::is_same_v<Output,
                                              ThermochimicaConfiguration::SpeciesOutput>)
              return archive_output.value("type", "") == "species" &&
                     archive_output.value("phase", "") == value.phase &&
                     archive_output.value("species", "") == value.species;
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::ElementPotentialOutput>)
              return archive_output.value("type", "") == "element_potential" &&
                     archive_output.value("element", "") == value.element;
            else if constexpr (std::is_same_v<Output,
                                              ThermochimicaConfiguration::VaporPressureOutput>)
              return archive_output.value("type", "") == "vapor_pressure" &&
                     archive_output.value("phase", "") == value.phase &&
                     archive_output.value("species", "") == value.species;
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::ElementDistributionOutput>)
              return archive_output.value("type", "") == "element_distribution" &&
                     archive_output.value("phase", "") == value.phase &&
                     archive_output.value("element", "") == value.element;
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::ChemicalPotentialOutput>)
            {
              const auto selector =
                  value.kind == ThermochimicaConfiguration::ChemicalPotentialKind::SPECIES
                      ? "species"
                  : value.kind == ThermochimicaConfiguration::ChemicalPotentialKind::QUADRUPLET
                      ? "quadruplet"
                      : "endmember";
              return archive_output.value("type", "") == "chemical_potential" &&
                     archive_output.value("phase", "") == value.phase &&
                     archive_output.value(selector, "") == value.component;
            }
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::PhaseGibbsEnergyOutput>)
              return archive_output.value("type", "") == "phase_gibbs" &&
                     archive_output.value("phase", "") == value.phase;
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::PhaseDrivingForceOutput>)
              return archive_output.value("type", "") == "phase_driving_force" &&
                     archive_output.value("phase", "") == value.phase;
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::SystemGibbsEnergyOutput>)
              return archive_output.value("type", "") == "system_gibbs";
            else if constexpr (std::is_same_v<
                                   Output,
                                   ThermochimicaConfiguration::SystemPropertyOutput>)
              return archive_output.value("type", "") == "system_property";
            else
              return archive_output.value("type", "") == "constituent_fraction" &&
                     archive_output.value("phase", "") == value.phase &&
                     archive_output.value("constituent", "") == value.constituent;
          },
          descriptor);
      if (outputs[output].value("variable", "") != variable ||
          !descriptor_matches ||
          outputs[output].value("extensive", false) !=
              static_cast<bool>(_configuration->output_extensive[output]) ||
          outputs[output].value("nonnegative", false) !=
              static_cast<bool>(_configuration->output_nonnegative[output]) ||
          outputs[output].value("fraction", false) !=
              static_cast<bool>(_configuration->output_fraction[output]))
      {
        fail("neural surrogate output " + std::to_string(output) + " ('" +
             outputs[output].value("variable", "") + "') does not match requested output '" +
             variable + "'");
        return;
      }
    }

    _neural_lower_bounds = metadata.at("input_lower_bounds").get<std::vector<Real>>();
    _neural_upper_bounds = metadata.at("input_upper_bounds").get<std::vector<Real>>();
    if (_neural_lower_bounds.size() != _configuration->inputWidth() ||
        _neural_upper_bounds.size() != _configuration->inputWidth())
    {
      fail("neural surrogate input width does not match the ChemicalComposition block");
      return;
    }

    torch::set_num_threads(1);
    _neural_model = std::make_unique<torch::jit::script::Module>(std::move(module));
  }
  catch (const std::exception & error)
  {
    fail("unable to load neural surrogate archive '" +
         std::string(_configuration->surrogate_archive) + "': " + error.what());
  }
}

void
ThermochimicaData::evaluateNeuralBatch()
{
  std::fill(_row_status, _row_status + _header->count, -1);
  if (!_neural_model || _neural_disabled)
  {
    for (const auto row : make_range(_header->count))
      _row_status[row] = solveRow(row, false);
    return;
  }

  std::vector<unsigned int> rows;
  std::vector<Real> total_scales;
  std::vector<float> inputs;
  rows.reserve(_header->count);
  total_scales.reserve(_header->count);
  inputs.reserve(_header->count * _configuration->inputWidth());
  unsigned int first_neural_row = 0;
  if (!_worker_has_previous_solve &&
      _configuration->warm_start == ThermochimicaConfiguration::WarmStart::PREVIOUS_SOLVE &&
      _header->count)
  {
    _row_status[0] = solveRow(0, false);
    first_neural_row = 1;
  }
  for (const auto row : make_range(first_neural_row, _header->count))
  {
    std::vector<Real> key;
    Real total_scale = 1.0;
    if (!normalizedInput(row, key, total_scale))
    {
      ++_header->invalid_state_rejections;
      continue;
    }
    bool in_bounds = true;
    for (const auto column : index_range(key))
    {
      const Real padding =
          1e-6 * std::max<Real>(1.0, std::max(std::abs(_neural_lower_bounds[column]),
                                             std::abs(_neural_upper_bounds[column])));
      if (key[column] < _neural_lower_bounds[column] - padding ||
          key[column] > _neural_upper_bounds[column] + padding)
      {
        in_bounds = false;
        break;
      }
    }
    if (!in_bounds)
    {
      ++_header->neural_out_of_bounds;
      continue;
    }
    rows.push_back(row);
    total_scales.push_back(total_scale);
    for (const auto value : key)
      inputs.push_back(static_cast<float>(value));
  }

  if (!rows.empty())
  {
    const auto inference_start = std::chrono::steady_clock::now();
    try
    {
      c10::InferenceMode guard;
      auto tensor =
          torch::from_blob(inputs.data(),
                           {static_cast<long>(rows.size()),
                            static_cast<long>(_configuration->inputWidth())},
                           torch::TensorOptions().dtype(torch::kFloat32))
              .clone();
      auto prediction = _neural_model->forward({tensor}).toTensor().to(torch::kCPU).contiguous();
      if (prediction.dim() != 2 || prediction.size(0) != static_cast<long>(rows.size()) ||
          prediction.size(1) != static_cast<long>(_configuration->outputWidth()))
        throw std::runtime_error("model returned an unexpected tensor shape");
      const auto values = prediction.accessor<float, 2>();
      ++_header->neural_batches;

      for (const auto index : index_range(rows))
      {
        const auto row = rows[index];
        auto * result = _results + row * _configuration->outputWidth();
        bool valid = true;
        for (const auto output : make_range(_configuration->outputWidth()))
        {
          Real value = values[index][output];
          if (_configuration->output_extensive[output])
            value *= total_scales[index];
          const Real invariant_padding = 1e-10;
          if (_configuration->output_nonnegative[output] && value < 0.0 &&
              value >= -invariant_padding)
            value = 0.0;
          if (_configuration->output_fraction[output] && value > 1.0 &&
              value <= 1.0 + invariant_padding)
            value = 1.0;
          if (!std::isfinite(value) || (_configuration->output_nonnegative[output] && value < 0.0) ||
              (_configuration->output_fraction[output] && value > 1.0))
          {
            valid = false;
            break;
          }
          result[output] = value;
        }
        if (!valid)
        {
          ++_header->invariant_rejections;
          continue;
        }

        ++_header->surrogate_hits;
        const bool audit =
            _configuration->surrogate_audit_interval &&
            (++_worker_accepted_predictions % _configuration->surrogate_audit_interval == 0);
        if (!audit)
        {
          _row_status[row] = 0;
          continue;
        }

        std::vector<Real> neural_result(result, result + _configuration->outputWidth());
        _row_status[row] = solveRow(row, false);
        if (_row_status[row] == 0)
        {
          ++_header->audits;
          if (!outputsWithinTolerance(neural_result, result))
          {
            ++_header->audit_failures;
            _neural_disabled = true;
            _header->neural_disabled = 1;
            for (const auto output : index_range(neural_result))
            {
              const Real tolerance =
                  _configuration->surrogate_absolute_tolerances[output] +
                  _configuration->surrogate_relative_tolerance *
                      std::max(std::abs(neural_result[output]), std::abs(result[output]));
              if (std::abs(neural_result[output] - result[output]) > tolerance)
              {
                const auto variable =
                    std::visit([](const auto & descriptor) { return outputVariable(descriptor); },
                               _configuration->outputs[output]);
                std::snprintf(_header->worker_error,
                              sizeof(_header->worker_error),
                              "Neural surrogate audit failed for '%s': predicted=%g, exact=%g, "
                              "tolerance=%g. Neural inference is disabled for this worker.",
                              variable.c_str(),
                              neural_result[output],
                              result[output],
                              tolerance);
                break;
              }
            }
          }
        }
      }
    }
    catch (const std::exception &)
    {
      ++_header->error_rejections;
      _neural_disabled = true;
      _header->neural_disabled = 1;
    }
    _header->neural_inference_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - inference_start).count();
  }

  for (const auto row : make_range(_header->count))
    if (_row_status[row] == -1)
      _row_status[row] = solveRow(row, false);
}
#endif

[[noreturn]] void
ThermochimicaData::workerLoop()
{
#ifdef MOOSE_LIBTORCH_ENABLED
  initializeNeuralSurrogate();
#endif
  initializeThermochimica();
#ifdef THERMOCHIMICA_ENABLED
  if ((_configuration->acceleration == ThermochimicaConfiguration::Acceleration::ADAPTIVE &&
       _configuration->surrogate_model != ThermochimicaConfiguration::SurrogateModel::NEURAL) ||
      _configuration->warm_start == ThermochimicaConfiguration::WarmStart::NEAREST_CACHED)
    _cache = std::make_unique<ValueCache<std::size_t>>(_configuration->inputWidth());
#endif
  writeMessage('I');
  if (_header->worker_status)
    _exit(1);
  while (true)
  {
    char message = 0;
    ssize_t received;
    do
      received = recv(_socket, &message, sizeof(message), 0);
    while (received < 0 && errno == EINTR);
    if (received == 0)
      _exit(0);
    if (received != sizeof(message))
      _exit(1);
    if (_header->command == static_cast<unsigned int>(Command::STOP))
    {
      writeMessage('R');
      _exit(0);
    }
    if (_header->command != static_cast<unsigned int>(Command::SOLVE))
    {
      _header->worker_status = EINVAL;
      writeMessage('R');
      continue;
    }

    const auto start = std::chrono::steady_clock::now();
#ifdef MOOSE_LIBTORCH_ENABLED
    if (_configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::NEURAL)
      evaluateNeuralBatch();
    else
#endif
      for (const auto row : make_range(_header->count))
        _row_status[row] = solveRow(row);
#ifdef THERMOCHIMICA_ENABLED
    _header->cache_entries = _cache ? _cache->size() : 0;
    _header->sensitivity_bytes = _worker_sensitivity_bytes;
    _header->cache_saturated =
        _cache && _cache->size() >= _configuration->cache_max_entries ? 1 : 0;
#endif
    _header->solve_seconds =
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    writeMessage('R');
  }
}

int
ThermochimicaData::solveRow(const unsigned int row, const bool allow_prediction)
{
#ifdef THERMOCHIMICA_ENABLED
  const auto * input = _inputs + row * _configuration->inputWidth();
  auto * result = _results + row * _configuration->outputWidth();
  std::fill(result, result + _configuration->outputWidth(), 0.0);
  _current_entity = _entity_ids[row];

  std::vector<Real> cache_key;
  Real total_scale = 1.0;
  const bool cacheable = _cache && normalizedInput(row, cache_key, total_scale);
  if (_cache && !cacheable)
    ++_header->invalid_state_rejections;
  bool audit = false;
  if (allow_prediction && cacheable &&
      _configuration->acceleration == ThermochimicaConfiguration::Acceleration::ADAPTIVE &&
      predictRow(row, cache_key, total_scale, audit) && !audit)
    return 0;

  Thermochimica::setUnitTemperature(_configuration->temperature_unit);
  Thermochimica::setUnitPressure(_configuration->pressure_unit);
  Thermochimica::setUnitMass(_configuration->composition_unit);
  Thermochimica::setTemperaturePressure(input[0], input[1]);
  Thermochimica::setElementMass(0, 0.0);
  for (const auto i : index_range(_configuration->element_ids))
    Thermochimica::setElementMass(_configuration->element_ids[i], input[2 + i]);

  const auto warm_start = _configuration->warm_start;
  bool nearest_loaded = false;
  if (warm_start == ThermochimicaConfiguration::WarmStart::PREVIOUS_TIMESTEP)
  {
    Thermochimica::resetReinit();
    if (loadPreviousState(_current_entity))
    {
      Thermochimica::setReinitRequested(true);
      ++_header->warm_starts;
    }
    else
      Thermochimica::setReinitRequested(false);
  }
  else if (warm_start == ThermochimicaConfiguration::WarmStart::NEAREST_CACHED)
  {
    Thermochimica::resetReinit();
    nearest_loaded = cacheable && loadNearestState(cache_key, total_scale);
    Thermochimica::setReinitRequested(nearest_loaded);
    if (nearest_loaded)
    {
      ++_header->warm_starts;
      ++_header->nearest_warm_starts;
    }
  }
  else
  {
    Thermochimica::setReinitRequested(warm_start ==
                                      ThermochimicaConfiguration::WarmStart::PREVIOUS_SOLVE);
    if (warm_start == ThermochimicaConfiguration::WarmStart::PREVIOUS_SOLVE &&
        _worker_has_previous_solve)
      ++_header->warm_starts;
  }

  Thermochimica::thermochimica();
  ++_header->exact_solves;
  auto solve_info = Thermochimica::checkInfoThermo();
  if (solve_info != 0 && nearest_loaded)
  {
    Thermochimica::resetThermo();
    Thermochimica::resetReinit();
    Thermochimica::resetInfoThermo();
    Thermochimica::setTemperaturePressure(input[0], input[1]);
    Thermochimica::setElementMass(0, 0.0);
    for (const auto i : index_range(_configuration->element_ids))
      Thermochimica::setElementMass(_configuration->element_ids[i], input[2 + i]);
    Thermochimica::setReinitRequested(false);
    Thermochimica::thermochimica();
    ++_header->exact_solves;
    ++_header->cold_retries;
    solve_info = Thermochimica::checkInfoThermo();
  }
  if (solve_info != 0)
    return solve_info;

  const bool retain_reinit = warm_start != ThermochimicaConfiguration::WarmStart::NONE ||
                             cacheable || _configuration->report_performance;
  std::optional<Thermochimica::ReinitializationData> reinit;
  std::vector<int> phase_signature;
  if (retain_reinit)
  {
    Thermochimica::saveReinitData();
    if (warm_start == ThermochimicaConfiguration::WarmStart::NEAREST_CACHED ||
        _configuration->report_performance)
    {
      reinit = Thermochimica::getReinitData();
      _header->gem_iterations += reinit->GEM_iterations;
    }
    if (cacheable)
      phase_signature = reinit ? reinit->assemblage : Thermochimica::getAssemblage();
    if (warm_start == ThermochimicaConfiguration::WarmStart::PREVIOUS_TIMESTEP)
      storePreviousState(_current_entity);
    else if (warm_start == ThermochimicaConfiguration::WarmStart::PREVIOUS_SOLVE)
      _worker_has_previous_solve = true;
  }

  if (const auto output_info = evaluateCurrentOutputs(row, result); output_info != 0)
    return output_info;
  bool audit_failed = false;
  if (audit)
  {
    ++_header->audits;
    if (!outputsWithinTolerance(_audit_prediction, result))
    {
      audit_failed = true;
      ++_header->audit_failures;
      if (_configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::KKT_LINEAR)
        shrinkAuditedEllipsoid(cache_key);
    }
  }
  const bool represented =
      cacheable &&
      _configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::KKT_LINEAR &&
      updateKktEllipsoid(cache_key, total_scale, phase_signature, result);
  if (cacheable && (!represented || audit_failed) &&
      _cache->size() < _configuration->cache_max_entries)
    cacheExactRow(row, cache_key, total_scale, phase_signature, reinit ? &*reinit : nullptr);
  return 0;
#else
  return ENOSYS;
#endif
}

#ifdef THERMOCHIMICA_ENABLED
int
ThermochimicaData::evaluateCurrentOutputs(const unsigned int row, Real * const result) const
{
  const auto * input = _inputs + row * _configuration->inputWidth();
  const auto total_input =
      std::accumulate(input + 2, input + _configuration->inputWidth(), Real(0));
  const bool use_indexed_outputs = std::all_of(input + 2,
                                               input + _configuration->inputWidth(),
                                               [total_input](const Real value)
                                               { return value > std::abs(total_input) * 1e-10; });
  const auto moles_phase =
      use_indexed_outputs ? std::vector<double>() : Thermochimica::getMolesPhase();
  Real phase_total = 0.0;
  if (_configuration->needs_phase_total)
  {
    for (const auto phase : index_range(_configuration->phase_indices))
      if (use_indexed_outputs)
      {
        const auto phase_result =
            Thermochimica::getPhaseMoles(_configuration->phase_indices[phase]);
        if (phase_result.second != 0)
          return phase_result.second;
        if (phase_result.first > 0.0)
          phase_total += phase_result.first;
      }
      else
      {
        const auto [phase_index, phase_info] =
            Thermochimica::getPhaseIndex(_configuration->phase_names[phase]);
        if (phase_info != 0)
          return phase_info;
        if (phase_index > 0 && moles_phase[phase_index - 1] > 0.0)
          phase_total += moles_phase[phase_index - 1];
      }
  }

  OutputEvaluationContext context{use_indexed_outputs, moles_phase, phase_total, input[1], {}};
  for (const auto output : index_range(_configuration->outputs))
  {
    const auto info = std::visit([&](const auto & descriptor)
                                 { return evaluateOutput(descriptor, context, result[output]); },
                                 _configuration->outputs[output]);
    if (info != 0)
      return info;
  }
  return 0;
}

bool
ThermochimicaData::normalizedInput(const unsigned int row,
                                   std::vector<Real> & key,
                                   Real & total_scale) const
{
  const auto * input = _inputs + row * _configuration->inputWidth();
  if (!std::all_of(input,
                   input + _configuration->inputWidth(),
                   [](const Real value) { return std::isfinite(value); }))
    return false;

  Real temperature_kelvin = input[0];
  if (_configuration->temperature_unit == "C")
    temperature_kelvin += 273.15;
  else if (_configuration->temperature_unit == "F")
    temperature_kelvin = (temperature_kelvin - 32.0) * 5.0 / 9.0 + 273.15;
  else if (_configuration->temperature_unit == "R")
    temperature_kelvin *= 5.0 / 9.0;

  Real pressure_bar = input[1];
  if (_configuration->pressure_unit == "atm")
    pressure_bar *= 1.01325;
  else if (_configuration->pressure_unit == "psi")
    pressure_bar *= 0.0689475729318;
  else if (_configuration->pressure_unit == "Pa")
    pressure_bar *= 1e-5;
  else if (_configuration->pressure_unit == "kPa")
    pressure_bar *= 1e-2;

  const auto * composition = input + 2;
  if (!std::all_of(composition,
                   input + _configuration->inputWidth(),
                   [](const Real value) { return value >= 0.0; }))
    return false;
  const Real total = std::accumulate(composition, input + _configuration->inputWidth(), Real(0));
  if (!(total > 0.0) || !(temperature_kelvin > 0.0) || !(pressure_bar > 0.0))
    return false;

  key.resize(_configuration->inputWidth());
  if (_configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::NEURAL)
  {
    key[0] = std::log(temperature_kelvin / 298.15);
    key[1] = std::log(pressure_bar);
    for (const auto i : index_range(_configuration->elements))
      key[2 + i] = composition[i] / total;
  }
  else if (_configuration->surrogate_model ==
           ThermochimicaConfiguration::SurrogateModel::KKT_LINEAR)
  {
    key[0] = std::log(temperature_kelvin / 298.15);
    key[1] = std::log(pressure_bar);
    const auto elements = _configuration->elements.size();
    for (const auto column : make_range(elements > 0 ? elements - 1 : 0))
    {
      const Real denominator = std::sqrt(Real((column + 1) * (column + 2)));
      Real coordinate = 0.0;
      for (const auto element : make_range(column + 1))
        coordinate += composition[element] / total / denominator;
      coordinate -= composition[column + 1] / total * Real(column + 1) / denominator;
      key[2 + column] = coordinate;
    }
    key.back() = _configuration->composition_is_fraction ? 0.0 : std::log(total);
  }
  else
  {
    key[0] = temperature_kelvin / 298.15;
    key[1] = pressure_bar;
    for (const auto i : index_range(_configuration->elements))
      key[2 + i] = composition[i] / total;
  }
  total_scale = _configuration->composition_is_fraction ? 1.0 : total;
  return true;
}

bool
ThermochimicaData::outputsWithinTolerance(const std::vector<Real> & expected,
                                          const Real * actual) const
{
  for (const auto output : index_range(expected))
  {
    const Real absolute = _configuration->surrogate_absolute_tolerances[output];
    const Real tolerance =
        absolute + _configuration->surrogate_relative_tolerance *
                       std::max(std::abs(expected[output]), std::abs(actual[output]));
    if (!std::isfinite(actual[output]) || std::abs(expected[output] - actual[output]) > tolerance)
      return false;
  }
  return true;
}

bool
ThermochimicaData::predictRow(const unsigned int row,
                              const std::vector<Real> & key,
                              const Real total_scale,
                              bool & audit)
{
  if (_configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::KKT_LINEAR)
    return predictKktRow(row, key, total_scale, audit);

  if (!_cache || !_cache->size())
  {
    ++_header->geometry_rejections;
    return false;
  }

  auto * result = _results + row * _configuration->outputWidth();
  const auto & [exact_key, exact_index, exact_distance] = _cache->getNeighbor(key);
  (void)exact_key;
  const auto & exact_record = _cache_records[exact_index];
  if (exact_distance <= 1e-24)
  {
    for (const auto output : index_range(exact_record.outputs))
      result[output] = exact_record.outputs[output] *
                       (_configuration->output_extensive[output] ? total_scale : 1.0);
    ++_header->exact_reuse_hits;
    return true;
  }

  const std::size_t dimension = key.size();
  const std::size_t requested_neighbors = _configuration->surrogate_neighbors
                                              ? _configuration->surrogate_neighbors
                                              : std::max<std::size_t>(2 * dimension + 1, 8);
  if (_cache->size() < requested_neighbors + 1)
  {
    ++_header->geometry_rejections;
    return false;
  }
  const auto neighbors = _cache->getNeighbors(key, requested_neighbors + 1);
  const auto & signature = _cache_records[std::get<1>(neighbors.front())].phase_signature;
  if (std::any_of(neighbors.begin(),
                  neighbors.end(),
                  [&](const auto & neighbor)
                  { return _cache_records[std::get<1>(neighbor)].phase_signature != signature; }))
  {
    ++_header->phase_rejections;
    return false;
  }

  for (const auto component : index_range(key))
  {
    Real minimum = std::numeric_limits<Real>::max();
    Real maximum = std::numeric_limits<Real>::lowest();
    for (const auto & neighbor : neighbors)
    {
      const auto value = std::get<0>(neighbor)[component];
      minimum = std::min(minimum, value);
      maximum = std::max(maximum, value);
    }
    const Real padding =
        1e-12 * std::max<Real>(1.0, std::max(std::abs(minimum), std::abs(maximum)));
    if (key[component] < minimum - padding || key[component] > maximum + padding)
    {
      ++_header->geometry_rejections;
      return false;
    }
  }

  // Reconstruct every neighbor from the remaining local cloud before trusting the query.
  for (const auto held : index_range(neighbors))
  {
    const auto & held_key = std::get<0>(neighbors[held]);
    const auto & held_record = _cache_records[std::get<1>(neighbors[held])];
    std::vector<Real> prediction(_configuration->outputWidth(), 0.0);
    Real weight_sum = 0.0;
    for (const auto candidate : index_range(neighbors))
      if (candidate != held)
      {
        const auto & candidate_key = std::get<0>(neighbors[candidate]);
        Real distance = 0.0;
        for (const auto component : index_range(held_key))
        {
          const Real delta = held_key[component] - candidate_key[component];
          distance += delta * delta;
        }
        const Real weight = 1.0 / std::max(distance, Real(1e-24));
        weight_sum += weight;
        const auto & values = _cache_records[std::get<1>(neighbors[candidate])].outputs;
        for (const auto output : index_range(prediction))
          prediction[output] += weight * values[output];
      }
    for (const auto output : index_range(prediction))
    {
      prediction[output] /= weight_sum;
      const Real absolute =
          _configuration->surrogate_absolute_tolerances[output] /
          (_configuration->output_extensive[output] ? held_record.total_scale : 1.0);
      const Real tolerance = absolute + _configuration->surrogate_relative_tolerance *
                                            std::max(std::abs(held_record.outputs[output]),
                                                     std::abs(prediction[output]));
      if (std::abs(held_record.outputs[output] - prediction[output]) > tolerance)
      {
        ++_header->error_rejections;
        return false;
      }
    }
  }

  std::vector<Real> prediction(_configuration->outputWidth(), 0.0);
  Real weight_sum = 0.0;
  for (const auto & neighbor : neighbors)
  {
    const Real weight = 1.0 / std::max(std::get<2>(neighbor), Real(1e-24));
    weight_sum += weight;
    const auto & values = _cache_records[std::get<1>(neighbor)].outputs;
    for (const auto output : index_range(prediction))
      prediction[output] += weight * values[output];
  }
  for (const auto output : index_range(prediction))
  {
    prediction[output] /= weight_sum;
    result[output] =
        prediction[output] * (_configuration->output_extensive[output] ? total_scale : 1.0);
    if (!std::isfinite(result[output]) ||
        (_configuration->output_nonnegative[output] && result[output] < 0.0) ||
        (_configuration->output_fraction[output] && result[output] > 1.0))
    {
      ++_header->invariant_rejections;
      return false;
    }
  }

  ++_worker_accepted_predictions;
  audit = _configuration->surrogate_audit_interval &&
          _worker_accepted_predictions % _configuration->surrogate_audit_interval == 0;
  if (audit)
    _audit_prediction.assign(result, result + _configuration->outputWidth());
  else
    ++_header->surrogate_hits;
  return true;
}

std::vector<Real>
ThermochimicaData::physicalInputDirection(const std::vector<Real> & internal_inputs,
                                          const unsigned int coordinate) const
{
  std::vector<Real> direction(internal_inputs.size(), 0.0);
  if (coordinate == 0)
    direction[0] = internal_inputs[0];
  else if (coordinate == 1)
    direction[1] = internal_inputs[1];
  else
  {
    const Real total = std::accumulate(internal_inputs.begin() + 2, internal_inputs.end(), 0.0);
    if (coordinate == internal_inputs.size() - 1)
    {
      if (!_configuration->composition_is_fraction)
        std::copy(internal_inputs.begin() + 2, internal_inputs.end(), direction.begin() + 2);
    }
    else
    {
      const auto column = coordinate - 2;
      const Real denominator = std::sqrt(Real((column + 1) * (column + 2)));
      for (const auto element : make_range(column + 1))
      {
        const auto [system_index, info] =
            Thermochimica::getElementIndex(_configuration->element_ids[element]);
        if (info != 0)
          return {};
        direction[2 + system_index] = total / denominator;
      }
      const auto [system_index, info] =
          Thermochimica::getElementIndex(_configuration->element_ids[column + 1]);
      if (info != 0)
        return {};
      direction[2 + system_index] = -total * Real(column + 1) / denominator;
    }
  }
  return direction;
}

bool
ThermochimicaData::buildKktSensitivity(CacheRecord & record,
                                       const unsigned int row,
                                       const std::vector<Real> & key)
{
  if (_configuration->needs_system_properties)
    return false;

  const auto start = std::chrono::steady_clock::now();
  const auto [qualified, qualification_info] =
      Thermochimica::getEquilibriumSensitivityQualification();
  if (qualification_info != 0 || !qualified)
  {
    ++_header->sensitivity_failures;
    if (qualification_info == 0)
      ++_header->unsupported_model_rejections;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }
  const auto [info, rcond] = Thermochimica::computeEquilibriumSensitivity();
  record.sensitivity_rcond = rcond;
  if (info != 0)
  {
    ++_header->sensitivity_failures;
    if (info == 3)
      ++_header->sensitivity_condition_rejections;
    else if (info == 4 || info == 5)
      ++_header->sensitivity_residual_rejections;
    else if (info == 6)
      ++_header->state_restore_failures;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }
  const auto diagnostics = Thermochimica::getEquilibriumSensitivityDiagnostics();
  if (diagnostics.status != 0 || !diagnostics.qualified)
  {
    ++_header->sensitivity_failures;
    ++_header->unsupported_model_rejections;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }
  const auto [internal_inputs, input_info] = Thermochimica::getEquilibriumSensitivityInputs();
  if (input_info != 0 || internal_inputs.size() != key.size())
  {
    ++_header->sensitivity_failures;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }
  const auto state = Thermochimica::getEquilibriumSensitivityState();
  if (state.status != 0 || state.parameters != internal_inputs.size())
  {
    ++_header->sensitivity_failures;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }

  const auto outputs = _configuration->outputWidth();
  const auto dimension = key.size();
  record.output_jacobian.assign(outputs * dimension, 0.0);
  record.state_log_amounts.assign(state.log_amounts.begin(), state.log_amounts.end());
  record.state_jacobian.assign(state.log_amounts.size() * dimension, 0.0);
  std::vector<Real> plus(outputs), minus(outputs), delta(internal_inputs.size());
  constexpr Real h = 1e-5;
  auto * mutable_input = _inputs + row * _configuration->inputWidth();
  const Real original_pressure = mutable_input[1];
  bool success = true;
  for (const auto coordinate : index_range(key))
  {
    const auto direction = physicalInputDirection(internal_inputs, coordinate);
    if (direction.size() != internal_inputs.size())
    {
      success = false;
      break;
    }
    for (const auto amount : index_range(record.state_log_amounts))
      for (const auto parameter : index_range(direction))
        record.state_jacobian[amount * dimension + coordinate] +=
            state.jacobian[amount * state.parameters + parameter] * direction[parameter];
    for (const auto sign : {-1, 1})
    {
      for (const auto component : index_range(delta))
        delta[component] = sign * h * direction[component];
      if (coordinate == 1)
        mutable_input[1] = original_pressure * (1.0 + sign * h);
      auto & values = sign > 0 ? plus : minus;
      const auto apply_info = Thermochimica::applyEquilibriumSensitivity(delta);
      if (apply_info != 0 || evaluateCurrentOutputs(row, values.data()) != 0)
      {
        if (apply_info == 3)
          ++_header->state_restore_failures;
        else if (apply_info == 4)
          ++_header->complementarity_rejections;
        success = false;
        break;
      }
      Real scale = record.total_scale;
      if (!_configuration->composition_is_fraction && coordinate == dimension - 1)
        scale *= 1.0 + sign * h;
      for (const auto output : index_range(values))
        if (_configuration->output_extensive[output])
          values[output] /= scale;
    }
    mutable_input[1] = original_pressure;
    if (!success)
      break;
    for (const auto output : index_range(plus))
    {
      const Real absolute = _configuration->surrogate_absolute_tolerances[output] /
                            (_configuration->output_extensive[output] ? record.total_scale : 1.0);
      const Real zero_floor = std::max(absolute, 1e-14);
      record.output_jacobian[output * dimension + coordinate] =
          std::max({std::abs(record.outputs[output]),
                    std::abs(plus[output]),
                    std::abs(minus[output])}) <= zero_floor
              ? 0.0
              : (plus[output] - minus[output]) / (2.0 * h);
    }
  }
  if (Thermochimica::restoreEquilibriumSensitivity() != 0)
  {
    ++_header->state_restore_failures;
    success = false;
  }
  mutable_input[1] = original_pressure;
  if (!success || !std::all_of(record.output_jacobian.begin(),
                               record.output_jacobian.end(),
                               [](const Real value) { return std::isfinite(value); }))
  {
    ++_header->sensitivity_failures;
    _header->sensitivity_seconds +=
        std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
    return false;
  }

  record.metric.assign(dimension * dimension, 0.0);
  for (const auto component : index_range(key))
    record.metric[component * dimension + component] = 1.0;
  for (const auto output : index_range(record.outputs))
  {
    const Real absolute = _configuration->surrogate_absolute_tolerances[output] /
                          (_configuration->output_extensive[output] ? record.total_scale : 1.0);
    const Real scale = std::max(absolute + _configuration->surrogate_relative_tolerance *
                                               std::abs(record.outputs[output]),
                                1e-14 * std::max(1.0, std::abs(record.outputs[output])));
    for (const auto i : index_range(key))
      for (const auto j : index_range(key))
        record.metric[i * dimension + j] += record.output_jacobian[output * dimension + i] *
                                            record.output_jacobian[output * dimension + j] /
                                            (scale * scale);
  }
  record.sensitivity_available = true;
  ++_header->sensitivity_successes;
  _header->sensitivity_seconds +=
      std::chrono::duration<Real>(std::chrono::steady_clock::now() - start).count();
  return true;
}

bool
ThermochimicaData::predictKktRow(const unsigned int row,
                                 const std::vector<Real> & key,
                                 const Real total_scale,
                                 bool & audit)
{
  if (!_cache || !_cache->size())
  {
    ++_header->geometry_rejections;
    return false;
  }
  auto * result = _results + row * _configuration->outputWidth();
  const auto & nearest = _cache->getNeighbor(key);
  const auto & nearest_record = _cache_records[std::get<1>(nearest)];
  if (std::get<2>(nearest) <= 1e-24)
  {
    for (const auto output : index_range(nearest_record.outputs))
      result[output] = nearest_record.outputs[output] *
                       (_configuration->output_extensive[output] ? total_scale : 1.0);
    ++_header->exact_reuse_hits;
    return true;
  }

  const auto requested = _configuration->surrogate_neighbors
                             ? _configuration->surrogate_neighbors
                             : std::max<std::size_t>(2 * key.size() + 1, 8);
  const auto neighbors =
      _cache->getNeighbors(key, std::min<std::size_t>(requested, _cache->size()));
  const auto & signature = _cache_records[std::get<1>(neighbors.front())].phase_signature;
  const auto & active_signature =
      _cache_records[std::get<1>(neighbors.front())].active_species_signature;
  const auto & assemblage_token =
      _cache_records[std::get<1>(neighbors.front())].assemblage_token;
  const bool mixed_signatures =
      std::any_of(neighbors.begin(),
                  neighbors.end(),
                  [&](const auto & neighbor)
                  {
                    const auto & record = _cache_records[std::get<1>(neighbor)];
                    return record.phase_signature != signature ||
                           record.active_species_signature != active_signature ||
                           record.assemblage_token != assemblage_token;
                  });
  if (mixed_signatures)
    ++_header->phase_rejections;
  if (neighbors.size() > 1)
  {
    const auto & second = _cache_records[std::get<1>(neighbors[1])];
    if (second.phase_signature != signature ||
        second.active_species_signature != active_signature ||
        second.assemblage_token != assemblage_token)
      return false;
  }

  std::size_t selected = std::numeric_limits<std::size_t>::max();
  Real selected_metric = std::numeric_limits<Real>::max();
  std::vector<Real> selected_delta(key.size());
  for (const auto & neighbor : neighbors)
  {
    const auto index = std::get<1>(neighbor);
    const auto & record = _cache_records[index];
    if (!record.sensitivity_available || record.phase_signature != signature ||
        record.active_species_signature != active_signature ||
        record.assemblage_token != assemblage_token)
      continue;
    std::vector<Real> delta(key.size()), metric_delta(key.size(), 0.0);
    for (const auto i : index_range(key))
      delta[i] = key[i] - record.coordinates[i];
    for (const auto i : index_range(key))
      for (const auto j : index_range(key))
        metric_delta[i] += record.metric[i * key.size() + j] * delta[j];
    const Real value = std::inner_product(delta.begin(), delta.end(), metric_delta.begin(), 0.0);
    if (value <= 1.0 && value < selected_metric)
    {
      selected = index;
      selected_metric = value;
      selected_delta = std::move(delta);
    }
  }
  if (selected == std::numeric_limits<std::size_t>::max())
  {
    ++_header->geometry_rejections;
    return false;
  }

  const auto & record = _cache_records[selected];
  for (const auto amount : index_range(record.state_log_amounts))
  {
    Real predicted_log_amount = record.state_log_amounts[amount];
    for (const auto component : index_range(key))
      predicted_log_amount +=
          record.state_jacobian[amount * key.size() + component] * selected_delta[component];
    if (!std::isfinite(predicted_log_amount) || predicted_log_amount <= std::log(1e-20))
    {
      ++_header->complementarity_rejections;
      return false;
    }
  }
  for (const auto output : index_range(record.outputs))
  {
    Real value = record.outputs[output];
    for (const auto component : index_range(key))
      value += record.output_jacobian[output * key.size() + component] * selected_delta[component];
    result[output] = value * (_configuration->output_extensive[output] ? total_scale : 1.0);
    if (!std::isfinite(result[output]) ||
        (_configuration->output_nonnegative[output] && result[output] < 0.0) ||
        (_configuration->output_fraction[output] && result[output] > 1.0))
    {
      ++_header->invariant_rejections;
      return false;
    }
  }

  ++_worker_accepted_predictions;
  audit = _configuration->surrogate_audit_interval &&
          _worker_accepted_predictions % _configuration->surrogate_audit_interval == 0;
  if (audit)
  {
    _audit_prediction.assign(result, result + _configuration->outputWidth());
    _audit_record = selected;
  }
  else
  {
    ++_header->surrogate_hits;
    ++_header->linear_retrieves;
  }
  return true;
}

bool
ThermochimicaData::loadNearestState(const std::vector<Real> & key, const Real total_scale)
{
  if (!_cache || !_cache->size())
    return false;
  const auto & record = _cache_records[std::get<1>(_cache->getNeighbor(key))];
  if (!record.reinit || !record.reinit->reinitAvailable)
    return false;
  auto reinit = *record.reinit;
  const Real ratio = total_scale / record.total_scale;
  for (auto & amount : reinit.molesPhase)
    amount *= ratio;
  Thermochimica::setReinitData(reinit);
  return true;
}

bool
ThermochimicaData::updateKktEllipsoid(const std::vector<Real> & key,
                                      const Real total_scale,
                                      const std::vector<int> & phase_signature,
                                      const Real * const exact_outputs)
{
  if (!_cache || !_cache->size())
    return false;
  auto signature = phase_signature;
  signature.erase(std::remove(signature.begin(), signature.end(), 0), signature.end());
  std::sort(signature.begin(), signature.end());
  const auto [active_signature, active_info] = Thermochimica::getActiveSolutionSpecies();
  if (active_info != 0)
    return false;
  const auto [assemblage_token, token_info] = Thermochimica::getEquilibriumAssemblageToken();
  if (token_info != 0)
    return false;
  const auto requested = _configuration->surrogate_neighbors
                             ? _configuration->surrogate_neighbors
                             : std::max<std::size_t>(2 * key.size() + 1, 8);
  const auto neighbors =
      _cache->getNeighbors(key, std::min<std::size_t>(requested, _cache->size()));
  for (const auto & neighbor : neighbors)
  {
    auto & record = _cache_records[std::get<1>(neighbor)];
    if (!record.sensitivity_available || record.phase_signature != signature ||
        record.active_species_signature != active_signature ||
        record.assemblage_token != assemblage_token)
      continue;
    std::vector<Real> delta(key.size()), metric_delta(key.size(), 0.0);
    for (const auto i : index_range(key))
      delta[i] = key[i] - record.coordinates[i];
    bool accurate = true;
    for (const auto output : index_range(record.outputs))
    {
      Real predicted = record.outputs[output];
      for (const auto component : index_range(key))
        predicted += record.output_jacobian[output * key.size() + component] * delta[component];
      const Real exact =
          exact_outputs[output] / (_configuration->output_extensive[output] ? total_scale : 1.0);
      const Real absolute = _configuration->surrogate_absolute_tolerances[output] /
                            (_configuration->output_extensive[output] ? total_scale : 1.0);
      const Real tolerance = absolute + _configuration->surrogate_relative_tolerance *
                                            std::max(std::abs(exact), std::abs(predicted));
      if (!std::isfinite(predicted) || std::abs(exact - predicted) > tolerance)
      {
        accurate = false;
        break;
      }
    }
    if (!accurate)
      continue;
    for (const auto i : index_range(key))
      for (const auto j : index_range(key))
        metric_delta[i] += record.metric[i * key.size() + j] * delta[j];
    const Real value = std::inner_product(delta.begin(), delta.end(), metric_delta.begin(), 0.0);
    if (value > 1.0)
    {
      const Real coefficient = (value - 1.0) / (value * value);
      for (const auto i : index_range(key))
        for (const auto j : index_range(key))
          record.metric[i * key.size() + j] -= coefficient * metric_delta[i] * metric_delta[j];
      ++_header->ellipsoid_growths;
    }
    return true;
  }
  return false;
}

void
ThermochimicaData::shrinkAuditedEllipsoid(const std::vector<Real> & key)
{
  if (_audit_record >= _cache_records.size())
    return;
  auto & record = _cache_records[_audit_record];
  std::vector<Real> delta(key.size()), metric_delta(key.size(), 0.0);
  for (const auto i : index_range(key))
    delta[i] = key[i] - record.coordinates[i];
  for (const auto i : index_range(key))
    for (const auto j : index_range(key))
      metric_delta[i] += record.metric[i * key.size() + j] * delta[j];
  const Real value = std::inner_product(delta.begin(), delta.end(), metric_delta.begin(), 0.0);
  const Real norm2 = std::inner_product(delta.begin(), delta.end(), delta.begin(), 0.0);
  if (norm2 > 0.0 && value <= 1.0)
  {
    const Real coefficient = (1.0 + 1e-6 - value) / (norm2 * norm2);
    for (const auto i : index_range(key))
      for (const auto j : index_range(key))
        record.metric[i * key.size() + j] += coefficient * delta[i] * delta[j];
    ++_header->ellipsoid_shrinks;
  }
  _audit_record = std::numeric_limits<std::size_t>::max();
}

void
ThermochimicaData::cacheExactRow(const unsigned int row,
                                 const std::vector<Real> & key,
                                 const Real total_scale,
                                 const std::vector<int> & phase_signature,
                                 const Thermochimica::ReinitializationData * const reinit)
{
  CacheRecord record;
  record.coordinates = key;
  const auto * result = _results + row * _configuration->outputWidth();
  record.outputs.assign(result, result + _configuration->outputWidth());
  for (const auto output : index_range(record.outputs))
    if (_configuration->output_extensive[output])
      record.outputs[output] /= total_scale;
  record.phase_signature = phase_signature;
  record.phase_signature.erase(
      std::remove(record.phase_signature.begin(), record.phase_signature.end(), 0),
      record.phase_signature.end());
  std::sort(record.phase_signature.begin(), record.phase_signature.end());
  const auto [active_signature, active_info] = Thermochimica::getActiveSolutionSpecies();
  if (active_info == 0)
    record.active_species_signature = active_signature;
  const auto [assemblage_token, token_info] = Thermochimica::getEquilibriumAssemblageToken();
  if (token_info == 0)
    record.assemblage_token = assemblage_token;
  record.total_scale = total_scale;
  if (_configuration->surrogate_model == ThermochimicaConfiguration::SurrogateModel::KKT_LINEAR)
  {
    if (active_info == 0 && token_info == 0)
      buildKktSensitivity(record, row, key);
    else
      ++_header->sensitivity_failures;
  }
  _worker_sensitivity_bytes +=
      (record.output_jacobian.capacity() + record.metric.capacity() +
       record.state_log_amounts.capacity() + record.state_jacobian.capacity()) * sizeof(Real);
  if (reinit && _configuration->warm_start == ThermochimicaConfiguration::WarmStart::NEAREST_CACHED)
    record.reinit = *reinit;
  _cache_records.push_back(std::move(record));
  _cache->insert(key, _cache_records.size() - 1);
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::PhaseOutput & output,
                                  OutputEvaluationContext & context,
                                  Real & value) const
{
  int info = 0;
  if (context.use_indexed_outputs)
  {
    const auto [moles, phase_info] = Thermochimica::getPhaseMoles(output.phase_index);
    value = moles;
    info = phase_info;
  }
  else
  {
    const auto [index, phase_info] = Thermochimica::getPhaseIndex(output.phase);
    value = phase_info == 0 && index > 0 ? context.moles_phase[index - 1] : 0.0;
    info = phase_info;
  }
  if (info == 0 && output.unit == ThermochimicaConfiguration::AmountUnit::MOLE_FRACTION)
    value = value > 0.0 && context.phase_total > 0.0 ? value / context.phase_total : 0.0;
  return info;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::SpeciesOutput & output,
                                  OutputEvaluationContext & context,
                                  Real & value) const
{
  int info = 0;
  if (output.is_mqm)
  {
    const auto pair = Thermochimica::getMqmqaPairMolFraction(output.phase, output.species);
    value = std::get<0>(pair);
    info = std::get<1>(pair);
    if (output.unit == ThermochimicaConfiguration::AmountUnit::MOLES && info == 0)
    {
      const auto pairs = Thermochimica::getMqmqaMolesPairs(output.phase);
      value *= std::get<0>(pairs);
      info += std::get<1>(pairs);
    }
  }
  else
  {
    const auto species_value =
        context.use_indexed_outputs
            ? Thermochimica::getOutputMolSpeciesPhase(output.phase_index, output.species_index)
            : Thermochimica::getOutputMolSpeciesPhase(output.phase, output.species);
    value = std::get<0>(species_value);
    info = std::get<1>(species_value);
    if (output.unit == ThermochimicaConfiguration::AmountUnit::MOLES)
    {
      if (context.use_indexed_outputs)
      {
        const auto phase = Thermochimica::getPhaseMoles(output.phase_index);
        value *= phase.first;
        if (phase.second != 0)
          return phase.second;
      }
      else
      {
        const auto [phase_index, phase_info] = Thermochimica::getPhaseIndex(output.phase);
        if (phase_info != 0)
          return phase_info;
        value = phase_index > 0 ? value * context.moles_phase[phase_index - 1] : 0.0;
      }
    }
  }

  if (info != 0 && info != 1)
    return info;
  if (info == 1)
    value = 0.0;
  return 0;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::ElementPotentialOutput & output,
                                  OutputEvaluationContext & context,
                                  Real & value) const
{
  const auto result = context.use_indexed_outputs
                          ? Thermochimica::getElementPotential(output.element_index)
                          : Thermochimica::getOutputChemPot(output.element);
  value = result.first;
  if (result.second != 0 && result.second != 1)
    return result.second;
  if (result.second == 1)
    value = 0.0;
  return 0;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::VaporPressureOutput & output,
                                  OutputEvaluationContext & context,
                                  Real & value) const
{
  const auto result =
      context.use_indexed_outputs
          ? Thermochimica::getOutputMolSpeciesPhase(output.phase_index, output.species_index)
          : Thermochimica::getOutputMolSpeciesPhase(output.phase, output.species);
  value = result.first * context.pressure;
  if (result.second != 0 && result.second != 1)
    return result.second;
  if (result.second == 1)
    value = 0.0;
  return 0;
}

int
ThermochimicaData::evaluateOutput(
    const ThermochimicaConfiguration::ElementDistributionOutput & output,
    OutputEvaluationContext & context,
    Real & value) const
{
  const auto result =
      context.use_indexed_outputs
          ? Thermochimica::getElementMolesInPhase(output.element_index, output.phase_index)
          : Thermochimica::getElementMolesInPhase(output.element, output.phase);
  value = result.second == 0 ? result.first : 0.0;
  if (result.second != 0 && result.second != 1 && result.second != 2)
    return result.second;

  if (output.unit == ThermochimicaConfiguration::DistributionUnit::FRACTION && value > 0.0)
  {
    const auto [it, inserted] = context.element_totals.try_emplace(output.element_index, 0.0, 0);
    if (inserted)
      for (const auto phase : index_range(_configuration->phase_names))
      {
        const auto phase_result =
            context.use_indexed_outputs
                ? Thermochimica::getElementMolesInPhase(output.element_index,
                                                        _configuration->phase_indices[phase])
                : Thermochimica::getElementMolesInPhase(output.element,
                                                        _configuration->phase_names[phase]);
        if (phase_result.second == 0 && phase_result.first > 0.0)
          it->second.first += phase_result.first;
        else if (phase_result.second != 1 && phase_result.second != 2)
        {
          it->second.second = phase_result.second;
          break;
        }
      }
    if (it->second.second != 0)
      return it->second.second;
    value = it->second.first == 0.0 ? 0.0 : value / it->second.first;
  }
  else if (output.unit == ThermochimicaConfiguration::DistributionUnit::FRACTION)
    value = 0.0;
  return 0;
}

int
ThermochimicaData::evaluateOutput(
    const ThermochimicaConfiguration::ChemicalPotentialOutput & output,
    OutputEvaluationContext & context,
    Real & value) const
{
  const auto phase_index =
      context.use_indexed_outputs ? output.phase_index : currentPhaseIndex(output.phase);
  if (phase_index < 0)
  {
    value = 0.0;
    return 0;
  }
  const auto component_index =
      context.use_indexed_outputs
          ? output.component_index
          : currentComponentIndex(phase_index, output.component, output.kind);
  if (component_index < 0)
  {
    value = 0.0;
    return 0;
  }

  const auto result =
      output.kind == ThermochimicaConfiguration::ChemicalPotentialKind::ENDMEMBER
          ? Thermochimica::getMqmqaEndmemberStoichiometricPotential(phase_index, component_index)
          : Thermochimica::getSpeciesChemicalPotential(phase_index, component_index);
  value = result.second == 0 ? result.first : 0.0;
  return result.second == 1 ? 0 : result.second;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::PhaseGibbsEnergyOutput & output,
                                  OutputEvaluationContext & context,
                                  Real & value) const
{
  const auto phase_index =
      context.use_indexed_outputs ? output.phase_index : currentPhaseIndex(output.phase);
  if (phase_index < 0)
  {
    value = 0.0;
    return 0;
  }
  const auto result = Thermochimica::getPhaseGibbsEnergy(phase_index);
  value = output.unit == ThermochimicaConfiguration::GibbsEnergyUnit::JOULES ? result.total
                                                                             : result.molar;
  if (result.status == 1)
  {
    value = 0.0;
    return 0;
  }
  return result.status;
}

int
ThermochimicaData::evaluateOutput(
    const ThermochimicaConfiguration::PhaseDrivingForceOutput & output,
    OutputEvaluationContext & context,
    Real & value) const
{
  const auto phase_index =
      context.use_indexed_outputs ? output.phase_index : currentPhaseIndex(output.phase);
  if (phase_index < 0)
  {
    value = 0.0;
    return 0;
  }
  const auto result = Thermochimica::getPhaseDrivingForce(phase_index);
  value = result.second == 0 ? result.first : 0.0;
  return result.second == 1 ? 0 : result.second;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::SystemGibbsEnergyOutput &,
                                  OutputEvaluationContext &,
                                  Real & value) const
{
  const auto result = Thermochimica::getSystemGibbsEnergy();
  value = result.first;
  return result.second;
}

int
ThermochimicaData::evaluateOutput(const ThermochimicaConfiguration::SystemPropertyOutput & output,
                                  OutputEvaluationContext &,
                                  Real & value) const
{
  const auto properties = Thermochimica::getHeatCapacityEnthalpyEntropy();
  if (output.property == ThermochimicaConfiguration::SystemPropertyKind::ENTHALPY)
    value = std::get<1>(properties);
  else if (output.property == ThermochimicaConfiguration::SystemPropertyKind::ENTROPY)
    value = std::get<2>(properties);
  else
    value = std::get<0>(properties);
  return 0;
}

int
ThermochimicaData::evaluateOutput(
    const ThermochimicaConfiguration::ConstituentFractionOutput & output,
    OutputEvaluationContext & context,
    Real & value) const
{
  auto phase_index = output.phase_index;
  auto constituent_index = output.constituent_index;
  if (!context.use_indexed_outputs)
  {
    phase_index = currentPhaseIndex(output.phase);
    if (phase_index < 0)
    {
      value = 0.0;
      return 0;
    }

    const auto constituents = Thermochimica::getConstituentsInPhase(phase_index);
    if (output.sublattice_index >= static_cast<int>(constituents.size()))
    {
      value = 0.0;
      return 0;
    }
    const auto & sublattice = constituents[output.sublattice_index];
    const auto constituent = std::find(sublattice.begin(), sublattice.end(), output.constituent);
    if (constituent == sublattice.end())
    {
      value = 0.0;
      return 0;
    }
    constituent_index = static_cast<int>(std::distance(sublattice.begin(), constituent));
  }

  const auto result = Thermochimica::getConstituentFraction(
      phase_index, output.sublattice_index, constituent_index);
  value = result.second == 0 ? result.first : 0.0;
  return result.second == 1 ? 0 : result.second;
}

bool
ThermochimicaData::loadPreviousState(const dof_id_type id)
{
  const auto slot_it = _previous_state_slots.find(id);
  if (slot_it == _previous_state_slots.end() || !_previous_state_available[slot_it->second])
    return false;

  const auto slot = slot_it->second;
  const auto integer_width = _reinit_elements + 169;
  const auto real_width = 2 * _reinit_elements + 2 * _reinit_species;
  auto * integers = _previous_state_integers.data() + slot * integer_width;
  auto * reals = _previous_state_reals.data() + slot * real_width;

  Thermochimica::setReinitData({integers,
                                reals,
                                reals + _reinit_elements,
                                reals + 2 * _reinit_elements,
                                reals + 2 * _reinit_elements + _reinit_species,
                                integers + _reinit_elements});
  return true;
}

void
ThermochimicaData::storePreviousState(const dof_id_type id)
{
  if (!_reinit_elements)
  {
    const auto sizes = Thermochimica::getReinitDataSizes();
    _reinit_elements = sizes.first;
    _reinit_species = sizes.second;
  }

  auto [slot_it, inserted] = _previous_state_slots.emplace(id, _previous_state_slots.size());
  const auto slot = slot_it->second;
  const auto integer_width = _reinit_elements + 169;
  const auto real_width = 2 * _reinit_elements + 2 * _reinit_species;
  if (inserted)
  {
    _previous_state_integers.resize((slot + 1) * integer_width);
    _previous_state_reals.resize((slot + 1) * real_width);
    _previous_state_available.resize(slot + 1);
  }

  auto * integers = _previous_state_integers.data() + slot * integer_width;
  auto * reals = _previous_state_reals.data() + slot * real_width;
  const auto [available, iterations] =
      Thermochimica::getReinitData({integers,
                                    reals,
                                    reals + _reinit_elements,
                                    reals + 2 * _reinit_elements,
                                    reals + 2 * _reinit_elements + _reinit_species,
                                    integers + _reinit_elements});
  (void)iterations;
  _previous_state_available[slot] = available;
}
#endif
