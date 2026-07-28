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

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"
export MOOSE_DEV_VERSION

# Capture the module-provided launcher before entering Python; shell aliases
# are otherwise unavailable to its subprocesses.
shopt -s expand_aliases
if ! type moose-dev-exec >/dev/null 2>&1; then
  echo "moose-dev-exec was not defined by ${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}" >&2
  exit 1
fi
if declare -F moose-dev-exec >/dev/null; then
  MOOSE_DEV_EXEC_DEFINITION="$(declare -f moose-dev-exec)"
  MOOSE_DEV_EXEC_DEFINITION="${MOOSE_DEV_EXEC_DEFINITION/#moose-dev-exec/thermochimica_moose_dev_exec}"
  eval "${MOOSE_DEV_EXEC_DEFINITION}"
elif alias moose-dev-exec >/dev/null 2>&1; then
  eval 'thermochimica_moose_dev_exec() { moose-dev-exec "$@"; }'
else
  MOOSE_DEV_EXEC_DEFINITION="$(type -P moose-dev-exec)"
  eval 'thermochimica_moose_dev_exec() { '"${MOOSE_DEV_EXEC_DEFINITION}"' "$@"; }'
fi
export -f thermochimica_moose_dev_exec

OUTPUT="${TC_RESULTS}/full_parallel_${SLURM_JOB_ID}"
DRIVER="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"
EXECUTABLE="${TC_REPO}/modules/chemical_reactions/chemical_reactions-opt"
CONTAINER_EXEC="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_adaptive/inl_moose_exec.sh"

mkdir -p "${OUTPUT}"
printf '%s\n' "${MOOSE_DEV_VERSION}" > "${OUTPUT}/inl_container_version.txt"
module list > "${OUTPUT}/modules.txt" 2>&1
mpiexec -n 2 "${CONTAINER_EXEC}" /bin/true

# For MPI configurations the driver constructs the INL-required ordering:
# mpiexec -n N moose-dev-exec chemical_reactions-opt ...
python3 "${DRIVER}" run \
  --tier full \
  --study parallel \
  --exe "${EXECUTABLE}" \
  --exec-prefix "${CONTAINER_EXEC}" \
  --mpiexec mpiexec \
  --skip-plots \
  --output "${OUTPUT}"
