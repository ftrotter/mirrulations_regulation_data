This directory contains a downloader that uses rclone to copy all or part of the
Mirrulations dataset to a local drive.

The public bucket supports anonymous access; AWS keys are not required. Copy
`rclone.config.example` to `rclone.config`, and copy `example.env` to `.env`.
Set the destination and rclone configuration paths in `.env`.

Then view the available download options:

```shell
python3 mirrulations_downloader.py --help
```

The downloader supports agency, year, docket, and text-only filters. Text-only
includes published TXT, JSON, HTM, and HTML objects. Docket
filters take precedence over agency and year filters, matching the original
downloader behavior. Filters cover both `raw-data/` and `derived-data/`.

For example, preview and confirm a text-only DEA download with:

```shell
python3 mirrulations_downloader.py --agency DEA --textonly
```

The first Markdown-enrichment development case uses:

```shell
python3 mirrulations_downloader.py --docket CMS-2026-1255 --textonly
```

Keep `MIRRULATIONS_DESTINATION_PATH` separate from `MARKDOWN_DB_PATH`. The
former is an exact source mirror; the latter defaults to
`./data/markdown_db/` and contains generated stage projections and metadata.
