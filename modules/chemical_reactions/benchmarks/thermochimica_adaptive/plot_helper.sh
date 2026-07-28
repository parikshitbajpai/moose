export TC_REPO=/home/bajpp/projects/tc_cache
export TC_RESULTS=/scratch/$USER/tc-results
export JOB_ID=2353405

DRIVER="$TC_REPO/modules/chemical_reactions/benchmarks/thermochimica_adaptive/benchmark.py"

for directory in "$TC_RESULTS"/full_*_"$JOB_ID"_*; do
  if [[ -s "$directory/runs.csv" &&
        -s "$directory/summary.csv" &&
        -s "$directory/accuracy.csv" ]]; then
    echo "Plotting $directory"
    python3 "$DRIVER" plot --input "$directory"
  else
    echo "Skipping incomplete directory: $directory"
  fi
done
