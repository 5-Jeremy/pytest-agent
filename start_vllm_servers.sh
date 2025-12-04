#!/bin/bash

# Usage: ./start_vllm_servers.sh <NUM_GPUS>

if [ "$#" -ne 1 ]; then
	echo "Usage: $0 <NUM_GPUS>"
	exit 1
fi

NUM_GPUS=$1
MODEL_NAME="Qwen/Qwen2.5-Coder-32B-Instruct"

echo "Starting vllm servers with $NUM_GPUS GPUs for $MODEL_NAME..."

for (( i=0; i<$NUM_GPUS; i++ )) do
    PORT=$((8000 + i))
    CUDA_VISIBLE_DEVICES=$i \
    python -m vllm.entrypoints.openai.api_server \
        --model $MODEL_NAME \
        --port $PORT \
        --max-num-batched-tokens 8192 &
done