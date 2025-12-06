# From inside the unittest-ai-agent directory, run "docker build -t unittest:docopt -f eval_dockerfiles/docopt/Dockerfile ."

FROM python:3.6-slim
WORKDIR /code
# Since we need a local version of the repo anyways, we can just copy it in
COPY eval_repos/docopt /code/repo/
# We delete the existing tests just in case. I'm not sure if pip install -e . will work though.
RUN cd ./repo && rm test_docopt.py && pip install pytest pytest-cov && pip install -e .