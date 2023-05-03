from __future__ import annotations

from typing import Dict

# The rest of the codebase uses bytes everywhere.
# Only use these units for user facing interfaces.
units: Dict[str, int] = {
    "hddcoin": 10**12,  # 1 hddcoin (HDD) is 1,000,000,000,000 byte (1 trillion)
    "byte": 1,
    "cat": 10**3,  # 1 CAT is 1000 CAT bytes
}
