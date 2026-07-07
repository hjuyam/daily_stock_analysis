#!/usr/bin/env python3
"""
DSA Single Stock Analyzer — lean wrapper, no noise.
Usage: python scripts/dsa_single.py <STOCK_CODE>
Output: single JSON line with analysis result.
"""
import os, sys, json

os.environ["WEBUI_ENABLED"] = "false"
os.environ["TQDM_DISABLE"] = "1"  # suppress progress bars
os.environ["ENV_FILE"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

# Suppress all logging ASAP
import logging
logging.getLogger().setLevel(logging.CRITICAL + 10)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Redirect stderr to /dev/null to suppress any remaining noise
_orig_stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')

from src.config import setup_env, get_config
setup_env()
config = get_config()

from src.core.pipeline import StockAnalysisPipeline
from src.logging_config import setup_logging

setup_logging()
# Kill all loggers after setup
for name in list(logging.root.manager.loggerDict):
    logging.getLogger(name).disabled = True
logging.root.disabled = True

stock_code = sys.argv[1].strip() if len(sys.argv) > 1 else ""
if not stock_code:
    sys.stderr = _orig_stderr
    print(json.dumps({"error": "No stock code provided"}))
    sys.exit(1)

pipeline = StockAnalysisPipeline(config=config)
results = pipeline.run(stock_codes=[stock_code], send_notification=False)

# Restore stderr for output
sys.stderr = _orig_stderr

for r in results:
    if r is None:
        continue
    code = getattr(r, 'code', '')
    if code == stock_code:
        print(json.dumps({
            "code": code,
            "name": getattr(r, 'name', ''),
            "score": getattr(r, 'sentiment_score', None),
            "trend": getattr(r, 'trend_prediction', ''),
            "advice": getattr(r, 'operation_advice', ''),
            "action": getattr(r, 'action', ''),
            "action_label": getattr(r, 'action_label', ''),
            "decision_type": getattr(r, 'decision_type', ''),
            "summary": (getattr(r, 'analysis_summary', '') or ''),
        }, ensure_ascii=False))
        sys.exit(0)

print(json.dumps({"error": f"No result for {stock_code}"}))
sys.exit(1)