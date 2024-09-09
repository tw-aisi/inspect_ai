import json
from datasets import load_dataset
from pathlib import Path
import os
import pandas as pd

dataset = load_dataset("princeton-nlp/SWE-bench_Verified")["test"]

# We create a subset of swe-bench which is just one example
dataset_one_sample = dataset.filter(lambda x: x["instance_id"] == "scikit-learn__scikit-learn-12585")

dataset_dir = Path(__file__).parent / "swebench_one_sample.hf"
os.makedirs(str(dataset_dir), exist_ok=True)
dataset_one_sample.to_parquet(dataset_dir / "dataset.parquet")


# We also create a subset of SWE-bench-verfied which:
# 1) Contains all of the repositories in SWE-bench verified
# 2) For each repository, contains an example where swe_agent + Claude 3.5 + Sonnet resolved the issue, and an example where it did not (Some repositories may not have examples where the issue was resolved, in this case we only include a single example where the issue was not resolved)
# The outputs of this script are cached as part of the respository, this script allows us to edit this the dataset.

results_per_repo = {}
logs_dir = Path(__file__).parent / "20240620_sweagent_claude3.5sonnet" / "logs" # To run this script, you must download local copy from https://github.com/swe-bench/experiments/tree/main/evaluation/verified/20240620_sweagent_claude3.5sonnet/
results = []
missing_results = []

# Load results from the log directory
for result in os.listdir(logs_dir):
    results_path = os.path.join(logs_dir, result,"report.json")
    if  os.path.exists(results_path):
        with open(results_path, "r") as f:
            result_dict = json.load(f)
            result_name, results_value = next(iter(result_dict.items()))
            output_dict = dict(instance_id=result_name,**results_value)
            patch_path = os.path.join(logs_dir, result,"patch.diff")
            with open(patch_path, "r") as f:
                output_dict["swe_agent_patch"] = f.read()
            results.append(output_dict)

    else:
        missing_results.append(result)

# Get repository name from the results
results = pd.DataFrame.from_records(results)
results["repo"] = results["instance_id"].apply(lambda x: x.split("__")[0])

# Github patches which change binary files cannot actually be applied. We wil remove these entries in the dataset
results = results[~results["swe_agent_patch"].str.contains("Binary files")]

# Group by repository, and success. Then pick one from each group.
results_per_repo = results.groupby(["repo", "resolved"])
results_per_repo = results_per_repo.apply(lambda x: x.sample(1)).reset_index(drop=True)


# Filter dataset by those instance ids, and add a "reolved_by_swe_agent" column.
instance_ids = results_per_repo["instance_id"].values
resolved = results_per_repo["resolved"].values

dataset = dataset.filter(lambda x: x["instance_id"] in instance_ids)
dataset = dataset.map(lambda x: dict(x, resolved_by_swe_agent=resolved[instance_ids == x["instance_id"]][0]), num_proc=4)
# Add swe-agent-patch
dataset = dataset.map(lambda x: dict(x, swe_agent_patch=results_per_repo[results_per_repo["instance_id"] == x["instance_id"]]["swe_agent_patch"].values[0]), num_proc=4)


# Calculate the accuracy. Should be 0.42857142857142855
accuracy = sum(resolved) / len(resolved)

# Save tbe dataset
dataset_dir = Path(__file__).parent / "all_repos_swe_agent_50_percent.hf"
os.makedirs(str(dataset_dir), exist_ok=True)
dataset.to_parquet(dataset_dir / "dataset.parquet")

print(f"Saved dataset to {dataset_dir}, accuracy {accuracy}")