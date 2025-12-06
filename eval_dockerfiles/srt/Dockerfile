# From inside the unittest-ai-agent directory, run "docker build -t unittest:srt -f eval_dockerfiles/srt/Dockerfile ."

FROM python:3.9-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/srt /code/repo/
# Note that this repo uses unittest for its tests, so the tests directory is not at the top level
RUN cd ./repo && rm -rf srt/tests/ && pip install pytest pytest-cov && pip install -e .