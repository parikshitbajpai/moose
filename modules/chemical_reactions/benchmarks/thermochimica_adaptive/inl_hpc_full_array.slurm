#!/bin/bash
#SBATCH --job-name=tc-adaptive
#SBATCH --partition=general
#SBATCH --array=0-13%4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=72:00:00
#SBATCH --exclusive
#SBATCH --output=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/out/tc-adaptive-%A_%a.out
#SBATCH --error=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/err/tc-adaptive-%A_%a.err
#SBATCH --wckey=neams
#SBATCH --mail-user=parikshit.bajpai@inl.gov
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

TC_REPO="${TC_REPO:-/home/bajpp/projects/tc_cache}"
: "${TC_RESULTS:?Set TC_RESULTS to persistent scratch storage}"
MOOSE_DEV_MPI="${MOOSE_DEV_MPI:-mpich}"
MOOSE_DEV_MODULE="moose-dev-${MOOSE_DEV_MPI}"
MPI_LAUNCHER="${MPI_LAUNCHER:-srun}"

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"

# Follow the same container-module setup used by MOOSE's RunHPC scheduler.
# Teton's moose-dev module advertises the host MPI/Apptainer modules that must
# be loaded in the batch environment.
read -r -a CONTAINER_REQUIRED_MODULES <<< "${CONTAINER_MODULE_REQUIRED_MODULES:-}"
if ((${#CONTAINER_REQUIRED_MODULES[@]})); then
  module unload "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"
  module load "${CONTAINER_REQUIRED_MODULES[@]}" "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"
fi
CONTAINER_EXEC_NAME="${CONTAINER_MODULE_EXEC:?The container module did not set CONTAINER_MODULE_EXEC}"
CONTAINER_EXEC="$(type -P "${CONTAINER_EXEC_NAME}" || true)"
if [[ ! -x "${CONTAINER_EXEC}" ]]; then
  echo "${CONTAINER_EXEC_NAME} is not an executable after loading the required modules" >&2
  exit 1
fi

STUDIES=(
  tolerance
  mesh
  elements
  fluoride_state_isolation
  inactive_msfl_fallback
  active_subq_fallback
  neighbors
  surrogate_model
  algorithm_comparison
  cache
  audit
  warm_start
  boundary
  output_cost
)

STUDY="${STUDIES[$SLURM_ARRAY_TASK_ID]}"
OUTPUT="${TC_RESULTS}/full_${STUDY}_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
DRIVER="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"
EXECUTABLE="${TC_REPO}/modules/chemical_reactions/chemical_reactions-opt"

mkdir -p "${OUTPUT}"
printf '%s\n' "${MOOSE_DEV_VERSION}" > "${OUTPUT}/inl_container_version.txt"
module list > "${OUTPUT}/modules.txt" 2>&1
"${CONTAINER_EXEC}" /bin/true

# The host Python driver needs only the standard library. Each MOOSE process
# uses the executable advertised by the loaded container module.
python3 "${DRIVER}" run \
  --tier full \
  --study "${STUDY}" \
  --exe "${EXECUTABLE}" \
  --exec-prefix "${CONTAINER_EXEC}" \
  --mpiexec "${MPI_LAUNCHER}" \
  --skip-plots \
  --output "${OUTPUT}"
