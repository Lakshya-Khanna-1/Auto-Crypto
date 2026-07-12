import sys
from pathlib import Path

# Add project root directory to sys.path to allow test collection to import tradecore
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
