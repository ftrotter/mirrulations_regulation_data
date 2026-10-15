# Running the Pipeline

This guide builds one bounded regulatory docket from acquisition through Stage
5 and the Neo4j graph bundle. Run commands from the repository root.

## Prerequisites

- Python 3 with `venv` support;
- `rclone` for public Mirrulations acquisition and verification;
- Docker with Compose only if Neo4j will be used; and
- provider API keys for the paid stages selected below.

```shell
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp example.env .env
```

`.env` is ignored by Git. Never commit it and never put secrets in versioned
YAML configuration.

## Create the API keys

Only configure providers that the selected run uses.

### Gemini API key

Gemini is the default provider in
`config/structure_discovery.example.yaml` for Stage 3 and direct Stage 4. The
production LangExtract topic stage also uses Gemini by default.

1. Sign in to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create or select a Google Cloud project when prompted.
3. Select **Create API key** and copy the new key.
4. Put it in local `.env`:

   ```dotenv
   GEMINI_API_KEY=replace-with-the-real-key
   ```

LangExtract also accepts `LANGEXTRACT_API_KEY`; `GEMINI_API_KEY` is the shared
repository setting. Verify that the requested model is available to the
selected project before starting a paid full-corpus run.

### OpenAI API key

OpenAI is required when Stage 3 or a premium Stage 4 run selects OpenAI, and for
the independent Stage 4 quality review.

1. Sign in to the [OpenAI API key page](https://platform.openai.com/api-keys).
2. Create a secret key in the intended project.
3. Copy it immediately; the secret is shown only at creation time.
4. Put it in `.env`:

   ```dotenv
   OPENAI_API_KEY=replace-with-the-real-key
   ```

API billing is separate from a ChatGPT subscription. Ensure the API project has
an appropriate budget before a managed run.

### Anthropic API key

Anthropic is required only when Stage 3 or a premium Stage 4 benchmark selects
Claude.

1. Sign in to the
   [Anthropic Console](https://console.anthropic.com/settings/keys).
2. Create a key in the intended workspace.
3. Copy it and put it in `.env`:

   ```dotenv
   ANTHROPIC_API_KEY=replace-with-the-real-key
   ```

Fund or enable billing for that Console workspace before a paid run.

### Regulations.gov API key

The core Mirrulations pipeline does not require this key. It is used by
`examples/regulation_gov_results/download_examples.py` and direct
Regulations.gov API experiments.

1. Request a key through the
   [Regulations.gov API documentation](https://open.gsa.gov/api/regulationsgov/).
2. Follow the emailed activation instructions.
3. Put it in `.env`:

   ```dotenv
   REGULATIONS_GOV_API_KEY=replace-with-the-real-key
   ```

## Configure paths

Use separate, non-overlapping source and generated-data roots:

```dotenv
MIRRULATIONS_DESTINATION_PATH=/absolute/path/to/mirrulations-source
MARKDOWN_DB_PATH=./data/markdown_db
RCLONE_CONFIG_FILE=/absolute/path/to/rclone.config
COMMENT_BROWSER_BASE_URL=http://127.0.0.1:8765
```

The examples below use development-validation docket `CMS-2026-1255`.

## 1. Acquire the docket

```shell
.venv/bin/python scripts/rclone/mirrulations_downloader.py \
  --docket CMS-2026-1255
```

The helper downloads from public bucket `s3://mirrulations`. Include original
PDF or DOCX objects when document structure recovery requires them. Run the
command with `--help` for agency, year, source-type, and destination options.

## 2. Generate Stage 1 and Stage 2

Verify the bounded mirror before generating Markdown:

```shell
.venv/bin/python scripts/markdown_enrichment.py \
  --source-root /absolute/path/to/mirrulations-source \
  --markdown-db data/markdown_db \
  --docket CMS-2026-1255 \
  --verify \
  --rclone-config /absolute/path/to/rclone.config
```

This produces semantic Stage 1 Markdown, citation-enriched Stage 2 Markdown,
block sidecars, inventories, manifests, annotations, friendly-name tables, and
reverse lookups.

Use `--normalize-json` only after fresh verification when pretty-printed source
JSON is desired. Original and normalized hashes are recorded. Use
`--title-requests-per-second` to pace official title lookups and
`--refresh-reference-titles` to retry cached failures.

## 3. Generate Stage 3 structure

The versioned YAML selects the provider and model; `.env` supplies its key.
Begin with one bounded paid call:

```shell
.venv/bin/python scripts/structure_discovery.py \
  --markdown-db data/markdown_db \
  --configuration config/structure_discovery.example.yaml \
  --document-limit 1 \
  --maximum-api-calls 1 \
  --dotenv .env
```

Review the result before increasing `--maximum-api-calls`. Request pacing,
concurrency, source filters, and segment-size bounds are explicit CLI options.
Completed segment hashes are reused.

For a deterministic sampled managed run, configure `STAGE3_REVIEW_*` in `.env`:

```shell
.venv/bin/python scripts/stage3_review.py start --sample-fraction 0.10
.venv/bin/python scripts/stage3_review.py status
.venv/bin/python scripts/stage3_review.py wait
```

For the full corpus with validated continuation into Stage 4:

```shell
.venv/bin/python scripts/stage3_review.py start \
  --sample-fraction 1.0 \
  --continue-with-stage4
```

Managed logs live under ignored `.local/pipeline_runs/`. Sample reports remain
separate from full-run reports.

## 4. Generate Stage 4 exact references

A direct bounded run using the reference model in the same YAML is:

```shell
.venv/bin/python scripts/reference_linker.py \
  --markdown-db data/markdown_db \
  --configuration config/structure_discovery.example.yaml \
  --maximum-api-calls 1 \
  --maximum-concurrency 1 \
  --requests-per-second 1 \
  --dotenv .env
```

Production alternatives are:

- `scripts/gemini_reference_linker.py`: Gemini full-context explicit caching;
- `scripts/premium_reference_linker.py`: isolated Gemini, Claude, or OpenAI
  provider benchmarks; and
- `scripts/stage4_quality_review.py`: independent OpenAI grading of a
  deterministic production sample.

Benchmark and quality-review outputs do not overwrite production Stage 4.
Successful batches and judgments are checkpointed. Budget exhaustion produces
an explicit attention-required state.

## 5. Run LangExtract and CorEx

Production extraction uses Gemini through LangExtract, then CorEx models the
eligible comment-block corpus without another pretrained language model:

```shell
.venv/bin/python scripts/topic_pipeline.py \
  --markdown-db data/markdown_db \
  --output-root data/markdown_db/metadata/topic_graph \
  --extraction-mode langextract \
  --model gemini-3.8-flash \
  --topic-count 20 \
  --assignment-threshold 0.9 \
  --maximum-topics-per-block 3
```

The model shown reflects the completed project run; model availability may vary
by Google project. Atomic `langextract_checkpoint.json` prevents repeat charges
for completed regulatory passages after interruption.

For credential-free development, use transparent rule-based agency anchors
while still fitting CorEx over real comment blocks:

```shell
.venv/bin/python scripts/topic_pipeline.py \
  --extraction-mode rule-based \
  --topic-count 20 \
  --assignment-threshold 0.9
```

The command writes Stage 5 Markdown, topic reports, assignments, provenance,
and `metadata/topic_graph/graph_bundle.json`. It aggregates accepted block
assignments into whole-comment `DISCUSSES_TOPIC` relationships for analysis.

## Check progress

```shell
.venv/bin/python scripts/pipeline_status.py --markdown-db data/markdown_db
```

Completion derives from generated artifacts and authoritative sidecars, not
logs or PID files. A stage is partial when expected records or coverage are
missing.

## Validate the result

```shell
.venv/bin/python scripts/validate_markdown_corpus.py \
  --source-root /absolute/path/to/mirrulations-source \
  --markdown-db data/markdown_db

.venv/bin/python scripts/neo4j_graph.py validate \
  --bundle data/markdown_db/metadata/topic_graph/graph_bundle.json

.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Live network tests are opt-in. For example,
`MIRRULATIONS_LIVE_CORNELL_TEST=1` enables the bounded Cornell title request.

## Analyze the completed regulation

Continue with [usage.md](usage.md) to start the comment browser and Neo4j,
import the graph, open the force-directed topical overview, and drill into exact
comment and regulatory passages.
