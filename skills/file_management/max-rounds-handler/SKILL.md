## Overview
When an autonomous exploration session hits the maximum number of rounds, it indicates the task requires more iterations than allowed. This skill describes how to analyze the situation and proceed without losing progress.

## When to Use
Use when you receive the "Max rounds reached" result from an exploration session.

## Core Pattern
1. **Read session logs** using `file_read(path="session_log.txt")` to understand what was completed.
2. **Search memory** for any partial results: `memory_search(query="last exploration result")`.
3. **Save current state** to a file: `code_run(language="python", code="with open('state.pkl','wb') as f: pickle.dump(state, f)")` (if applicable).
4. **Determine required extra rounds** based on remaining steps. Optionally use `web_scraper(url="https://example.com/guidelines")` to check best practices.
5. **Restart the exploration** with increased max_rounds parameter: e.g., `code_run(language="python", code="explore_task(task, max_rounds=300)")`.
6. **Load saved state** at the beginning of the new session to continue from where you left off.

## Common Mistakes
- Not saving intermediate results before the max rounds hit.
- Ignoring the limit and retrying with the same parameters, leading to infinite loops.
- Forgetting to load the saved state, causing duplicate work.