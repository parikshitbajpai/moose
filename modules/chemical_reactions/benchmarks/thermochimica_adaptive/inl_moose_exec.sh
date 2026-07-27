#!/bin/bash

set -euo pipefail

# The parent Slurm shell captures the module-provided moose-dev-exec alias or
# function while Lmod is available and exports this callable to its children.
if ! declare -F thermochimica_moose_dev_exec >/dev/null; then
  echo "thermochimica_moose_dev_exec was not exported by the Slurm launcher" >&2
  exit 127
fi

thermochimica_moose_dev_exec "$@"
