#!/bin/bash
# Wrapper to run sync jobs with venv activated

cd "$(dirname "$0")"
source venv/bin/activate
python -m backend.run_sync_jobs
