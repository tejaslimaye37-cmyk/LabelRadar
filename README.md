# LabelRadar: Regulatory Drug Label-Change Intelligence

LabelRadar helps users understand how official drug labels change over
time. It retrieves Structured Product Labeling (SPL) data from openFDA,
compares label versions section by section, stores the results, and uses
AI to create readable summaries.

> **Project status:** Development prototype. AI-generated summaries must
> be checked against original label text and are not intended to
> independently support clinical, safety, or regulatory decisions.

## What It Does

-   Collects drug label versions from openFDA.
-   Identifies additions, removals, and modifications between label
    sections.
-   Tracks changes using version identifiers and effective dates.
-   Stores label and change information in Neo4j and PostgreSQL.
-   Uses an OpenAI-compatible language-model interface to summarize
    changes.
-   Provides a web dashboard and API for exploring results.

Development and testing have included **Lipitor** and **Keytruda**.

## How It Works

``` mermaid
flowchart TD
    A[Drug label data from openFDA] --> B[Ingest label versions]
    B --> C[Extract label sections]
    C --> D[Compare versions and calculate diffs]
    D --> E[Store data in PostgreSQL and Neo4j]
    E --> F[Analyze changes with the configured LLM]
    F --> G[Review results in the dashboard or API]
```

## Technology Stack

  -----------------------------------------------------------------------
  Technology                          Purpose
  ----------------------------------- -----------------------------------
  Python 3.12                         Main programming language

  FastAPI                             Asynchronous backend and REST API

  Pydantic v2 and pydantic-settings   Data validation and application
                                      configuration

  Neo4j 5.20+                         Graph storage for drugs, label
                                      versions, sections, and change
                                      relationships

  PostgreSQL 16 with pgvector         Relational database with
                                      vector-extension support

  SQLAlchemy 2.0 async and asyncpg    Asynchronous PostgreSQL access

  Neo4j Python driver                 Application connectivity to Neo4j

  OpenAI-compatible LLM client        Common interface for supported
                                      language-model endpoints

  MLX-LM and Qwen3.5-4B-8bit          Local AI setup used for development
                                      on Apple Silicon

  Docker and Docker Compose           Runs the application and database
                                      services

  pytest and respx                    Automated testing and HTTP mocking

  Ruff                                Python linting and import
                                      formatting

  GitHub Actions                      Automated linting and tests in CI
  -----------------------------------------------------------------------

## Architecture and Graph Model

LabelRadar uses two data stores for different purposes:

-   **Neo4j** represents relationships between drugs, label versions,
    sections, and changes.
-   **PostgreSQL** stores relational application data. The configured
    PostgreSQL image includes pgvector support.

  ----------------------------------------------------------------------------------
  Node or relationship                           Meaning
  ---------------------------------------------- -----------------------------------
  `(:Drug)`                                      A drug identified by name and its
                                                 stable `spl_set_id`

  `(:LabelVersion)`                              A label revision with a
                                                 `version_id` and `effective_date`

  `(:Section)`                                   A label section, such as
                                                 `boxed_warning`,
                                                 `warnings_and_precautions`, or
                                                 `contraindications`

  `(:Drug)-[:HAS_VERSION]->(:LabelVersion)`      Connects a drug to its label
                                                 versions

  `(:LabelVersion)-[:HAS_SECTION]->(:Section)`   Connects a version to its sections

  `[:CHANGED_TO]`                                Represents a change between
                                                 corresponding sections across
                                                 versions
  ----------------------------------------------------------------------------------

Change records can include a change type (`added`, `removed`,
`modified`, or `unchanged`), a text diff, line counts, and a similarity
ratio, depending on the comparison output.

## Quickstart

### Prerequisites

-   Python 3.12
-   Docker Desktop with Docker Compose
-   Git
-   For the local MLX setup: a compatible Apple Silicon Mac, MLX-LM, and
    the model available locally

### 1. Get the code and install dependencies

``` bash
git clone <repository-url>
cd LabelRadar

python3.12 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
```

Replace `<repository-url>` with your repository URL. Review `.env` and
set the values required by your configuration. Do not commit secrets or
API keys.

### 2. Start the services

Build the images and start the application and database containers:

``` bash
docker compose up --build -d
```

If your checkout includes the startup script for the local MLX model,
use it for the full local-LLM setup:

``` bash
./scripts/start_labelradar.sh
```

The first Docker startup may take longer while images are downloaded and
the application image is built.

### 3. Open LabelRadar

  ---------------------------------------------------------------------------------
  Service                 URL                               Notes
  ----------------------- --------------------------------- -----------------------
  Dashboard               http://localhost:8000/dashboard   Browser interface

  Swagger UI              http://localhost:8000/docs        Explore and call API
                                                            endpoints

  ReDoc                   http://localhost:8000/redoc       Alternative API
                                                            documentation

  Neo4j Browser           http://localhost:7474             Graph database
                                                            interface

  PostgreSQL              `localhost:5432`                  Host connection, if the
                                                            port is published

  MLX model API           http://127.0.0.1:8080/v1/models   Available when MLX-LM
                                                            is running on the host
  ---------------------------------------------------------------------------------

Use the database credentials configured in `.env` or Docker Compose. Do
not assume development credentials are suitable for production.

## LLM Configuration

LabelRadar uses an OpenAI-compatible client. Configure
`OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `LLM_MODEL` for the model
server you use.

### Local MLX setup

The current development setup runs MLX-LM on the Mac host on port
`8080`:

``` bash
HF_HUB_OFFLINE=1 mlx_lm.server \
  --model mlx-community/Qwen3.5-4B-8bit \
  --host 127.0.0.1 \
  --port 8080
```

For the FastAPI application running **inside Docker**, use:

``` dotenv
OPENAI_BASE_URL=http://host.docker.internal:8080/v1
OPENAI_API_KEY=local
LLM_MODEL=mlx-community/Qwen3.5-4B-8bit
```

If FastAPI runs directly on the Mac, use `http://127.0.0.1:8080/v1`
instead.

### Other OpenAI-compatible endpoints

Example Ollama-compatible configuration:

``` dotenv
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=qwen2.5:latest
```

Example hosted OpenAI configuration:

``` dotenv
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=<your-api-key>
LLM_MODEL=gpt-4o-mini
```

Other compatible providers, including vLLM or Groq, may work with their
appropriate endpoint, API key, and model identifier. Follow each
provider's documentation for exact values.

> **Docker networking:** `localhost` inside a container refers to that
> container. Use `host.docker.internal` to reach a model server running
> on the Mac host. Port `8080` is used for MLX to avoid conflicting with
> FastAPI on port `8000`.

## API Reference

Open [Swagger UI](http://localhost:8000/docs) to see the exact routes,
request schemas, and response models exposed by the running application.

The API prefix is configurable through `API_V1_PREFIX` (typically
`/api/v1`). Use Swagger to confirm exact paths in your current checkout.

### Ingest drug labels

**Purpose:** Retrieve label versions, extract sections, calculate
differences, and save the results.

Example request body:

``` json
{
  "drug_name": "Lipitor",
  "spl_set_id": null,
  "max_versions": 20
}
```

The response can report the normalized drug name, SPL Set ID, number of
versions ingested, sections created, diffs computed, and details for
each version.

### Query the change timeline

**Purpose:** Retrieve changes between versions of a drug.

Depending on the API schema, filters may include:

-   `drug_name` --- drug to inspect
-   `section_name` --- optional section filter, such as `boxed_warning`
    or `contraindications`
-   `change_type` --- optional filter such as `added`, `removed`, or
    `modified`

A change record may include source and target version IDs, effective
date, section name, change type, text diff, added and removed line
counts, similarity ratio, and a short summary.

### Health check

**Purpose:** Check application and database connectivity.

The health response may include application status, environment, and
Neo4j/PostgreSQL connectivity. Refer to Swagger for the actual response
schema.

## Testing and Code Quality

Run from the project root with the virtual environment activated:

``` bash
# Run the test suite
pytest -v

# Run tests with coverage (if pytest-cov is installed)
pytest -v --cov=app --cov-report=term-missing

# Check code quality
ruff check .

# Apply supported automatic lint fixes
ruff check . --fix
```

The project uses pytest and HTTP mocking support. GitHub Actions is
configured to run linting and tests in CI.

## Stopping the Services

Stop Docker Compose containers:

``` bash
docker compose down
```

Named database volumes are normally preserved. If MLX-LM was started
separately on the Mac host, stop it separately---for example, with
`Ctrl+C` in its terminal or using the PID recorded by the startup
script.

Avoid commands that remove Docker volumes unless you intentionally want
to delete stored database data.

## Limitations and Responsible Use

-   Historical version availability and completeness depend on the
    upstream source and ingestion settings.
-   A text difference does not automatically mean a change is clinically
    significant.
-   AI summaries can omit context or be incorrect; verify important
    claims against the original labels.
-   LabelRadar is a development prototype, not a validated clinical
    decision-support or regulatory-compliance system.

## License

The original README includes an MIT license badge. Confirm that the
repository contains the corresponding `LICENSE` file before distributing
the project under the MIT License.
