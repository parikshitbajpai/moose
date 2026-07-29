export TC_REPO=/home/bajpp/projects/tc_cache
export TC_RESULTS=/scratch/$USER/tc-results
# export JOB_ID=2353405
# export JOB_ID=2353440
export JOB_ID=2354756 # Parallel


DRIVER="$TC_REPO/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"

shopt -s nullglob
for directory in "$TC_RESULTS"/full_*_"$JOB_ID" "$TC_RESULTS"/full_*_"$JOB_ID"_*; do
  if [[ -f "$directory/runs.csv" &&
        -f "$directory/summary.csv" &&
        $(wc -l < "$directory/runs.csv") -gt 1 &&
        $(wc -l < "$directory/summary.csv") -gt 1 ]]; then
    echo "Plotting: $directory"
    python3 "$DRIVER" plot --input "$directory"
  else
    echo "Skipping incomplete/failed: $directory"
  fi
done
shopt -u nullglob
