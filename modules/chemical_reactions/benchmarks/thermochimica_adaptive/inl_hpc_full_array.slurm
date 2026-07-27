#!/bin/bash
#SBATCH --job-name=tc-adaptive
#SBATCH --partition=general
#SBATCH --array=0-13%4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=72:00:00
#SBATCH --exclusive
#SBATCH --output=tc-adaptive-%A_%a.out
#SBATCH --error=tc-adaptive-%A_%a.err

set -euo pipefail

: "${TC_REPO:?Set TC_REPO to the repository root}"
: "${TC_RESULTS:?Set TC_RESULTS to persistent scratch storage}"

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "moose-dev-openmpi/${MOOSE_DEV_VERSION}"

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

# The host Python driver needs only the standard library. Each MOOSE process is
# entered through moose-dev-exec, including every command recorded in metadata.
python3 "${DRIVER}" run \
  --tier full \
  --study "${STUDY}" \
  --exe "${EXECUTABLE}" \
  --exec-prefix moose-dev-exec \
  --mpiexec mpiexec \
  --skip-plots \
  --output "${OUTPUT}"
