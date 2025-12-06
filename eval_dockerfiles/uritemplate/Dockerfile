# From inside the unittest-ai-agent directory, run "docker build -t unittest:uritemplate -f eval_dockerfiles/uritemplate/Dockerfile ."

FROM python:3.9-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/uritemplate /code/repo/
# In this repo, the tests directory is at the top level
RUN cd ./repo && rm -rf tests/ && pip install pytest pytest-cov && pip install -e .