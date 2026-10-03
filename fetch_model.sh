#!/usr/bin/env bash
# Download the local embedding model so the browser can run semantic recall
# fully offline (no huggingface.co access at runtime).
#
# Serves Xenova/paraphrase-multilingual-MiniLM-L12-v2 (multilingual MiniLM,
# 384-dim, works on Nepali + English) under models/. app.py mounts that
# directory at /models and memory.js loads it via localModelPath: "./models".
#
# Usage:  ./fetch_model.sh
set -euo pipefail

cd "$(dirname "$0")"
MODEL_DIR="models/Xenova/paraphrase-multilingual-MiniLM-L12-v2"
BASE="https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main"

mkdir -p "$MODEL_DIR/onnx"

files=(
  "config.json"
  "tokenizer.json"
  "tokenizer_config.json"
  "special_tokens_map.json"
  "unigram.json"
  "onnx/model_quantized.onnx"
)

for f in "${files[@]}"; do
  dest="$MODEL_DIR/$f"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "skip (exists): $f"
  else
    echo "fetch: $f"
    curl -sL --retry 3 -o "$dest" "$BASE/$f"
  fi
done

echo
echo "Done. Model files in $MODEL_DIR:"
du -sh "$MODEL_DIR"
