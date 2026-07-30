#!/bin/bash
#SBATCH --job-name=tc-nn-qualification
#SBATCH --array=0-6%3
#SBATCH --partition=general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=72:00:00
#SBATCH --output=tc-nn-%A_%a.out
#SBATCH --error=tc-nn-%A_%a.err
#SBATCH --wckey=neams
#SBATCH --mail-user=parikshit.bajpai@inl.gov
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail

TC_REPO="${TC_REPO:-/home/bajpp/projects/tc_cache}"
: "${TC_NN_WORKDIR:?Set TC_NN_WORKDIR to persistent scratch storage}"
TC_ML_ENV="${TC_ML_ENV:-ml}"
MOOSE_DEV_MPI="${MOOSE_DEV_MPI:-mpich}"
MOOSE_DEV_MODULE="moose-dev-${MOOSE_DEV_MPI}"
DRIVER="${TC_REPO}/modules/chemical_reactions/benchmarks/thermochimica_neural/qualification.py"
EXECUTABLE="${TC_REPO}/modules/chemical_reactions/chemical_reactions-opt"
COMBINED_EXECUTABLE="${TC_REPO}/modules/combined/combined-opt"

module purge
module load use.moose versioner
MOOSE_DEV_VERSION="$("${TC_REPO}/scripts/versioner.py" moose-dev)"
module load "${MOOSE_DEV_MODULE}/${MOOSE_DEV_VERSION}"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "${TC_ML_ENV}"
PYTHON="$(command -v python)"
export TC_NN_THREADS="${TC_NN_THREADS:-${SLURM_CPUS_PER_TASK:-1}}"

STUDIES=(fe_cr fluoride ns elements elements elements stress)
ELEMENT_COUNTS=(0 0 0 9 13 17 0)
STUDY="${STUDIES[${SLURM_ARRAY_TASK_ID}]}"
ELEMENT_COUNT="${ELEMENT_COUNTS[${SLURM_ARRAY_TASK_ID}]}"
OUTPUT="${TC_NN_WORKDIR}/${STUDY}_${ELEMENT_COUNT}_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
ELEMENT_ARGUMENTS=()
if [[ "${STUDY}" == "elements" ]]; then
  ELEMENT_ARGUMENTS=(--element-count "${ELEMENT_COUNT}")
fi

[[ -f "${DRIVER}" ]] || { echo "Missing qualification driver: ${DRIVER}" >&2; exit 1; }
[[ -x "${EXECUTABLE}" ]] || { echo "Missing Chemical Reactions executable: ${EXECUTABLE}" >&2; exit 1; }
if [[ "${STUDY}" == "ns" && ! -x "${COMBINED_EXECUTABLE}" ]]; then
  echo "Missing combined executable: ${COMBINED_EXECUTABLE}" >&2
  exit 1
fi

mkdir -p "${OUTPUT}"
printf '%s\n' "${MOOSE_DEV_VERSION}" > "${OUTPUT}/inl_container_version.txt"
printf '%s\n' "$(git -C "${TC_REPO}" rev-parse HEAD)" > "${OUTPUT}/source_revision.txt"
module list > "${OUTPUT}/modules.txt" 2>&1
conda list --explicit > "${OUTPUT}/conda_environment.txt"

moose-dev-exec "${PYTHON}" "${DRIVER}" "${STUDY}" \
  --tier full \
  --workdir "${OUTPUT}" \
  --app "${EXECUTABLE}" \
  --combined-app "${COMBINED_EXECUTABLE}" \
  "${ELEMENT_ARGUMENTS[@]}" \
  "$@"
