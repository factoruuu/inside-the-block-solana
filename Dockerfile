FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Keys and data are provided at runtime via volumes/env — never baked in.
ENTRYPOINT ["itb"]
CMD ["plan"]
