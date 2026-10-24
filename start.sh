#!/usr/bin/env bash
# Check laptop prerequisites, then start the local draft server.
set -euo pipefail

cd "$(dirname "$0")"

need() {
  echo "Missing: $1" >&2
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  need "python3. Install Python 3.10 or newer."
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(
        f"Python 3.10 or newer is required. This machine has {sys.version.split()[0]}."
    )
PY

if ! command -v ollama >/dev/null 2>&1; then
  need "the ollama command. Install it from https://ollama.com/download and open the Ollama app once."
fi

if ! curl -sf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null; then
  need "a running Ollama server. Open the Ollama app, or run: ollama serve"
fi

missing=0
while read -r model; do
  [ -n "$model" ] || continue
  if ! ollama list | awk 'NR > 1 { print $1 }' | grep -Eq "^${model}(:|$)"; then
    echo "Model not installed: $model" >&2
    echo "  ollama pull $model" >&2
    missing=1
  fi
done <<'MODELS'
mistral-small3.2
gemma4:12b
MODELS

if [ "$missing" -ne 0 ]; then
  exit 1
fi

echo "Starting on http://127.0.0.1:8765"
exec python3 server.py
