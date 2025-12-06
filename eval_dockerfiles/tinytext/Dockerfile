# From inside the unittest-ai-agent directory, run "docker build -t unittest:tinytext -f eval_dockerfiles/tinytext/Dockerfile ."

FROM python:3.10.19-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/tinytext /code/repo/
RUN cd ./repo && rm -rf tests/ && pip install pytest pytest-cov
