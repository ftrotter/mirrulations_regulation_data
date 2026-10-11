This directory contains a downloader that uses rclone to copy all or part of the
Mirrulations dataset to a local drive.

The public bucket supports anonymous access; AWS keys are not required. Copy
`rclone.config.example` to `rclone.config`, and copy `example.env` to `.env`.
Set the destination and rclone configuration paths in `.env`.

Then view the available download options:

```shell
python3 mirrulations_downloader.py --help
```

The downloader supports agency, year, docket, and text-only filters. Docket
filters take precedence over agency and year filters, matching the original
downloader behavior. Filters cover both `raw-data/` and `derived-data/`.

For example, preview and confirm a text-only DEA download with:

```shell
python3 mirrulations_downloader.py --agency DEA --textonly
```
