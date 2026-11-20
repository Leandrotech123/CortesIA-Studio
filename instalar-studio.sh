#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(realpath -- "$0")")"
for ferramenta in python3 ffmpeg ffprobe curl; do
  command -v "$ferramenta" >/dev/null || { echo "Instale $ferramenta no Ubuntu e tente novamente."; exit 1; }
done
mkdir -p tmp cache/models logs
export TMPDIR="$PWD/tmp" PIP_CACHE_DIR="$PWD/cache/pip" HF_HOME="$PWD/cache/huggingface"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [[ ! -s cache/models/small/model.bin || ! -s cache/models/small/tokenizer.json ]]; then
  .venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download('Systran/faster-whisper-small',
                  revision='536b0662742c02347bc0e980a01041f333bce120',
                  local_dir='cache/models/small')
PY
fi
echo 'Instalação concluída. Abra o Studio com Abrir CortesIA Studio.cmd.'
