# From inside the unittest-ai-agent directory, run "docker build -t unittest:untangle -f eval_dockerfiles/untangle/Dockerfile ."

FROM python:3.9-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/untangle /code/repo/
# In this repo, the tests directory is at the top level
RUN cd ./repo && rm -rf tests/ && pip install pytest pytest-cov && pip install -e .