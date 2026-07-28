#!/bin/bash
#SBATCH --job-name=tc-parallel
#SBATCH --partition=general
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=72:00:00
#SBATCH --exclusive
#SBATCH --output=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/out/tc-parallel-%j.out
#SBATCH --error=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/err/tc-parallel-%j.err

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

# Match MOOSE's Teton RunHPC setup: load the host container/MPI modules
# advertised by the selected moose-dev module and use its executable wrapper.
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

OUTPUT="${TC_RESULTS}/full_parallel_${SLURM_JOB_ID}"
DRIVER="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"
EXECUTABLE="${TC_REPO}/modules/chemical_reactions/chemical_reactions-opt"

mkdir -p "${OUTPUT}"
printf '%s\n' "${MOOSE_DEV_VERSION}" > "${OUTPUT}/inl_container_version.txt"
module list > "${OUTPUT}/modules.txt" 2>&1
"${MPI_LAUNCHER}" -n 2 "${CONTAINER_EXEC}" /bin/true

# Teton uses srun for MPI configurations.
python3 "${DRIVER}" run \
  --tier full \
  --study parallel \
  --exe "${EXECUTABLE}" \
  --exec-prefix "${CONTAINER_EXEC}" \
  --mpiexec "${MPI_LAUNCHER}" \
  --skip-plots \
  --output "${OUTPUT}"
