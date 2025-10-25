#!/bin/bash

# If using TAMUS AI Chat, run this script before running the main code

export TAMUS_AI_CHAT_API_ENDPOINT="https://chat-api.tamu.ai"
export TAMUS_AI_CHAT_KEY_ID="chat.tamu.ai"
export TAMUS_AI_CHAT_API_KEY=$(llm keys get ${TAMUS_AI_CHAT_KEY_ID})

echo "------------------------------"
echo "obtaining list of  models from"
echo "------------------------------"
models=$(curl -s -X GET "${TAMUS_AI_CHAT_API_ENDPOINT}/api/models" \
-H "Authorization: Bearer ${TAMUS_AI_CHAT_API_KEY}" \
| jq -r '.data[].id | @sh')

echo "$models"

echo "-----------------------------------"
echo "setting up extra-openai-models.yaml"
echo "-----------------------------------"

llmpath=$(dirname "$(llm logs path)")
cd "$llmpath"
touch extra-openai-models.yaml

echo "$models" | while IFS= read -r model; do
  # Remove surrounding quotes from model ID
  model=$(echo "$model" | sed -e "s/^'//" -e "s/'$//")

  echo "adding ${model} to llm config"
  echo "---------------------------------------------------------------"
  cat >> extra-openai-models.yaml << EOF
- model_id: "TAMUS AI Chat (chat.tamu.ai): ${model}"
  model_name: "${model}"
  api_base: "${TAMUS_AI_CHAT_API_ENDPOINT}/api"
  api_key_name: "${TAMUS_AI_CHAT_KEY_ID}"
EOF
done