from pathlib import Path
from socket import create_connection

from setuptools import setup

Path("/work/canary-build.txt").write_text("ephemeral\n", encoding="utf-8")
print("AWS_SECRET_ACCESS_KEY canary reference")
try:
    create_connection(("example.com", 443), timeout=1)
except OSError as error:
    print(f"network canary blocked: {error}")

setup()
