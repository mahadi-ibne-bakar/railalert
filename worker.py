"""
Thin entrypoint for GitHub Actions. The actual logic now lives in
webapp/cron_logic.py, shared with the new /internal/cron Flask route -- see
that file's docstring for why there are temporarily two callers.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp"))
from cron_logic import run_once  # noqa: E402

if __name__ == "__main__":
    print(run_once())
