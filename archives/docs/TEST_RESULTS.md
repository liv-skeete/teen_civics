# Orchestrator Tweet Format Test

## Objective
Verify the new tweet post format with the optimized link display by running the orchestrator in a dry-run mode.

## Test Steps
1.  **Created a test script:** A test script, `scripts/test_tweet_format.py`, was created to execute the orchestrator in dry-run mode.
2.  **Executed the test script:** The script was run to fetch a recent bill and generate the tweet content without posting to Twitter.
3.  **Verified the output:** The output of the script was monitored to confirm the new tweet format.

## Results
The test was successful. The orchestrator ran in dry-run mode and generated the following tweet content for bill `s1872-119`:

```
🏛️ Today in Congress

The Senate passed the Critical Infrastructure Manufacturing Feasibility Act requiring a study on domestic manufacturing capabilities for power grids and water systems.

👉 See how this affects you: teencivics.org/bill/critical-infrastructure-manufacturing-feasibility-act-s1872119
```

This output confirms that the new tweet format, including the header, summary, and the optimized link to the bill, is working as expected.