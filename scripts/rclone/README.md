This directory has a series of rclone commands that can be used to clone all or some of the mirrulations data to a local drive. 

In order to use it, you need to get the appropriate keys from Amazon, and then copy rclone.conf.example to rclone.conf, and put your keys inside!! 

Then run 

```
python mirrulations_downloader.py
```
And it should guide you through your download options. 

```
Options:
  -a, --agency TEXT  Agency name(s) separated by commas.
  -y, --year TEXT    Year(s) or range(s) of years separated by commas or dash
                     (e.g., 2010-2015).
  --textonly         Flag to indicate if textonly should be True.
  --getall           Download all agencies, all years. (WARNING: this could
                     cost a few hundred dollars...)
  --transfers TEXT   How many rclone connections to run at the same time
                     (default is 50)
  -d, --docket TEXT  Download a specific docket id
  --help             Show this message and exit
```
