FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .
COPY . .
CMD ["python", "-m", "orchestrator.run_loop"]
