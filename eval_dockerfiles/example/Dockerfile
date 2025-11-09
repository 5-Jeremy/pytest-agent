# From inside the unittest-ai-agent directory, run "docker build -t unittest:example -f eval_dockerfiles/Dockerfile ."

FROM python:3.10.19-slim
WORKDIR /code
# In practice, this would be replaced with git clone
COPY example/ /code/example/
RUN cd ./example && rm -rf tests/ && pip install pytest pytest-cov

# Can use ENTRYPOINT to make a script execute immediately when container starts