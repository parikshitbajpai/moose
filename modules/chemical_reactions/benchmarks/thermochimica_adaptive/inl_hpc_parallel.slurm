#!/bin/bash
#SBATCH --job-name=tc-parallel
#SBATCH --partition=general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=72:00:00
#SBATCH --exclusive
#SBATCH --output=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/out/tc-parallel-%j.out
#SBATCH --error=/home/bajpp/projects/tc_cache/modules/chemical_reactions/benchmarks/thermochimica_adaptive/err/tc-parallel-%j.err
#SBATCH --wckey=neams
#SBATCH --mail-user=parikshit.bajpai@inl.gov
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

TC_REPO="${TC_REPO:-/home/bajpp/projects/tc_cache}"
: "${TC_RESULTS:?Set TC_RESULTS to persistent scratch storage}"
MOOSE_DEV_MPI="${MOOSE_DEV_MPI:-mpich}"
MOOSE_DEV_MODULE="moose-dev-${MOOSE_DEV_MPI}"

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"

CONTAINER_EXEC="$(type -P moose-dev-exec || true)"
if [[ ! -x "${CONTAINER_EXEC}" ]]; then
  echo "moose-dev-exec is not an executable after loading ${MOOSE_DEV_MODULE}" >&2
  exit 1
fi

OUTPUT="${TC_RESULTS}/full_parallel_${SLURM_JOB_ID}"
DRIVER="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"
EXECUTABLE="${TC_REPO}/modules/chemical_reactions/chemical_reactions-opt"

mkdir -p "${OUTPUT}"
printf '%s\n' "${MOOSE_DEV_VERSION}" > "${OUTPUT}/inl_container_version.txt"
module list > "${OUTPUT}/modules.txt" 2>&1
"${CONTAINER_EXEC}" env HYDRA_LAUNCHER=fork mpiexec -n 2 /bin/hostname

# Enter the container once; the driver launches MPI ranks inside it.
"${CONTAINER_EXEC}" env HYDRA_LAUNCHER=fork python "${DRIVER}" run \
  --tier full \
  --study parallel \
  --exe "${EXECUTABLE}" \
  --mpiexec mpiexec \
  --skip-plots \
  --output "${OUTPUT}"
