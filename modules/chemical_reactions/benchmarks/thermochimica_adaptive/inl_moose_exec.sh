#!/bin/bash

set -euo pipefail

: "${MOOSE_DEV_VERSION:?Set MOOSE_DEV_VERSION to the version selected by versioner.py}"

# The INL module exposes moose-dev-exec as a shell alias or function rather
# than an executable on PATH. Reload the selected module in this Bash process
# and use eval so aliases are expanded after the module has been loaded.
shopt -s expand_aliases
module unload "moose-dev-openmpi/${MOOSE_DEV_VERSION}" >/dev/null 2>&1 || true
module load use.moose "moose-dev-openmpi/${MOOSE_DEV_VERSION}"
eval 'moose-dev-exec "$@"'
