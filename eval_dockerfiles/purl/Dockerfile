# From inside the unittest-ai-agent directory, run "docker build -t unittest:purl -f eval_dockerfiles/purl/Dockerfile ."

FROM python:3.8-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/purl /code/repo/
# In this repo, the tests directory is at the top level
RUN cd ./repo && rm -rf tests/ && pip install pytest pytest-cov && pip install -e .