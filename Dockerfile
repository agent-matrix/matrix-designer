# Matrix Designer — the Brain, as a standalone HTTP service.
#
#   docker build -t matrix-designer .
#   docker run -p 8077:8077 matrix-designer
#       POST /design/blueprints {idea}          -> 3 blueprints + details
#       POST /design/refine     {idea, message} -> orchestrator chat refinement
#       POST /design/bundle     {idea, candidate_id} -> the full Design Bundle, validated
#       POST /design/review     {bundle}        -> schema + design-rule verdict
#       GET  /healthz
#
# Hardening (all optional, default off — see src/matrix_designer/service.py):
#   -e MATRIX_DESIGNER_API_KEY=...           require a key on /design/*
#   -e MATRIX_DESIGNER_CORS_ORIGINS=https://build.matrixhub.io
#   -e MATRIX_DESIGNER_ALLOWED_PROVIDERS=ollabridge,watsonx
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MATRIX_DESIGNER_PORT=8077 \
    MATRIX_DESIGNER_HOST=0.0.0.0

WORKDIR /app
COPY . /app

# Install with the HTTP service + MCP extras. Add the agentic backends with:
#   pip install ".[service,mcp,agentic,langgraph]"
RUN pip install --upgrade pip && pip install ".[service,mcp]"

# Drop privileges.
RUN useradd --system --create-home --uid 1000 designer && chown -R designer:designer /app
USER designer

EXPOSE 8077
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MATRIX_DESIGNER_PORT\",\"8077\")}/healthz').read()" || exit 1

CMD ["python", "-m", "matrix_designer.service"]
