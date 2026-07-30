set -euo pipefail

TC_REPO="${TC_REPO:-/home/bajpp/projects/tc_cache}"
TC_RESULTS="${TC_RESULTS:-/scratch/$USER/tc-results}"
: "${JOB_ID:?Set JOB_ID to the Slurm array job ID}"
PYTHON="${PYTHON:-python3}"

DRIVER="$TC_REPO/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"

shopt -s nullglob
directories=("$TC_RESULTS"/full_*_"$JOB_ID"_*)
if ((${#directories[@]} == 0)); then
  echo "No result directories found for job $JOB_ID beneath $TC_RESULTS" >&2
  exit 1
fi

for directory in "${directories[@]}"; do
  if [[ -s "$directory/runs.csv" &&
        -s "$directory/summary.csv" &&
        -s "$directory/accuracy.csv" ]]; then
    echo "Plotting $directory"
    "$PYTHON" "$DRIVER" plot --input "$directory"
  else
    echo "Skipping incomplete directory: $directory"
  fi
done
