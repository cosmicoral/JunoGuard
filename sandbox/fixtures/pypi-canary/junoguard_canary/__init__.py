from pathlib import Path

Path("/work/canary-import.txt").write_text("ephemeral\n", encoding="utf-8")
