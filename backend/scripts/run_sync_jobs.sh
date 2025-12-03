#!/bin/bash
# Wrapper to run sync jobs with venv activated

# Change to project root (parent of scripts directory)
cd "$(dirname "$0")/../.."
source venv/bin/activate
python -m backend.jobs.run_sync_jobs
