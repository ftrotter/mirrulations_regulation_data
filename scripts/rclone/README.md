This directory has a series of rclone commands that can be used to clone all or some of the mirrulations data to a local drive. 

In order to use it, you need to get the appropriate keys from Amazon, and then copy rclone.conf.example to rclone.conf, and put your keys inside!! 

Then run 

```
mirrulations_downloader.py
```
And it should guide you through your download options. 

We are able to make this data affordable for us to host, by allowing each downloader to pay using the [Amazon S3 Downloader pays option](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RequesterPaysBuckets.html). Generally, downloading all of the text is not that expensive, well under $100. But downloading again and again can be expensive, so be mindful of the costs as you run these scripts. Generally, the whole point of this project is to make the files available as text to avoid downloading pdfs, or other binary files which can get expensive. 

The key to getting these command to work is to use the requester_pays flag in the rclone configuration file: 

Here is the link to the relevant page from the rclone documentation.

https://rclone.org/s3/#s3-requester-pays

