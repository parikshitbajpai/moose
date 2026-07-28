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

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"

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

# All full-array studies are single-rank. Enter the container once around the
# driver so its MOOSE subprocesses execute in the same container environment.
moose-dev-exec python3 "${DRIVER}" run \
  --tier full \
  --study "${STUDY}" \
  --exe "${EXECUTABLE}" \
  --skip-plots \
  --output "${OUTPUT}"
