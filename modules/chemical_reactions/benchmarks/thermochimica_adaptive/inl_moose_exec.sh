#!/bin/bash

set -euo pipefail

# Teton's environment may include the current directory in PATH. The MOOSE
# repository contains an apptainer/ directory, which must not shadow the real
# apptainer executable used by moose-dev-exec.
ORIGINAL_IFS="${IFS}"
IFS=:
read -r -a PATH_ENTRIES <<< "${PATH}"
IFS="${ORIGINAL_IFS}"
SANITIZED_PATH=""
for PATH_ENTRY in "${PATH_ENTRIES[@]}"; do
  if [[ -z "${PATH_ENTRY}" || "${PATH_ENTRY}" == "." || -d "${PATH_ENTRY}/apptainer" ]]; then
    continue
  fi
  SANITIZED_PATH="${SANITIZED_PATH:+${SANITIZED_PATH}:}${PATH_ENTRY}"
done
export PATH="${SANITIZED_PATH}"
unset ORIGINAL_IFS PATH_ENTRIES PATH_ENTRY SANITIZED_PATH

APPTAINER_EXECUTABLE="$(type -P apptainer || true)"
if [[ ! -f "${APPTAINER_EXECUTABLE}" || ! -x "${APPTAINER_EXECUTABLE}" ]]; then
  echo "No executable apptainer command was found in the sanitized PATH" >&2
  exit 127
fi
unset APPTAINER_EXECUTABLE

# The parent Slurm shell captures the module-provided moose-dev-exec alias or
# function while Lmod is available and exports this callable to its children.
if ! declare -F thermochimica_moose_dev_exec >/dev/null; then
  echo "thermochimica_moose_dev_exec was not exported by the Slurm launcher" >&2
  exit 127
fi

thermochimica_moose_dev_exec "$@"
