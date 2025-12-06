#!/bin/bash

LIST=(parse portion purl python-pathspec srt tomli untangle uritemplate url-normalize)

for NAME in "${LIST[@]}"; do
	poetry run ut generate eval_repos/$NAME -c eval_$NAME
done