"""Make `juno_mcp` importable without installing the MCP SDK.

`juno_mcp.integrity` is deliberately stdlib-only, so these tests run under any
interpreter — including the backend virtualenv that CI already builds.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
