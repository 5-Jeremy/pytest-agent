# From inside the unittest-ai-agent directory, run "docker build -t unittest:DottedDict -f eval_dockerfiles/DottedDict/Dockerfile ."

FROM python:3.9-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/DottedDict /code/repo/
# Note that this repo uses unittest for its tests, so the tests directory is not at the top level
RUN cd ./repo && rm -rf dotted/tests/ && pip install pytest pytest-cov && pip install -e .
