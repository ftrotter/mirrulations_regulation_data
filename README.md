# Mirrulations Regulation Data
A repository with instructions for accessing data from the mirrulations project. 

## S3 Access
The Mirrulations project publishes its results at the following S3 Bucket. 

```
s3://mirrulations
```

Mirrulations uses 


## Data License

Regulations data is public domain under the [edicts of government](https://en.wikipedia.org/wiki/Edict_of_government) principle. 

With this in mind, we are formally labeling the data as Public Domain, by using the [Creative Commons Public Domain mark](https://creativecommons.org/publicdomain/mark/1.0/):

<p xmlns:dct="http://purl.org/dc/terms/">
<a rel="license" href="http://creativecommons.org/publicdomain/mark/1.0/">
<img src="http://i.creativecommons.org/p/mark/1.0/88x31.png"
     style="border-style: none;" alt="Public Domain Mark" />
</a>
<br />
This work (<span property="dct:title">Mirrulations Regulation Data</span>, by <a href="https://regulations.gov" rel="dct:creator"><span property="dct:title">Participants in pulic regulatory process</span></a>), identified by <a href="https://github.com/MoravianUniversity/mirrulations" rel="dct:publisher"><span property="dct:title">Mirrulations Project</span></a>, is free of known copyright restrictions.
</p>

We have also added a text version of this assertion in the data_LICENSE.txt file. 

At one time, regulations.gov requested that data downloaded from the service include the following warning: 

```
Regulations.gov and the Federal government cannot verify and are not responsible for the accuracy or authenticity of the data or analyses derived from the data after the data has been retrieved from Regulations.gov.

In other words, "once the data has been downloaded from Regulations.gov, the U.S. Government cannot verify and is not responsible for the quality, accuracy, reliability, or timeliness of any analyses conducted using the downloaded data."
```
Indeed mirrulations uses the Regulations.gov Data API but is neither endorsed nor certified by Regulations.gov.


## Warnings

There are unique risks associated with this public dataset, please read these warnings carefully.

### Data Reliability Warning
The public domain status of this information means that you are free to use this data in any way that you would like. 
However, please note that much of our data is the results of the use of the Mirrulations Software, which, amoung other 
things, converts PDF to Text in various ways. This process can have bugs and as a result, it is possible that the text
generated by these processes is incorrect, incomplete or otherwise broken. The MIT license of the Mirrulations makes it clear
that we are fully disclaiming the liability for the use of the program, which means using the data is at your own risk. 
There are no warranties from us that the data is correct. 

### Privacy Warning

Further, many people likely did not understand that by contribiting to the regulatory comment process, they contributed their 
data to the public sphere. Many commenters appear to be assuming that only government regulators would be able to see and a
access their data. This means that it is likely that there is a substantial amount of data inside these comments that
people consider private, despite the fact that they have actually made it public information. Please be considerate 
to this risk as much as possible and do not use this data in a manner which takes advantage of this misunderstanding.
In a similar fashion, it is possible that people contributed data without fully understanding how this data could be 
used against them. In the era of Facebook and other companies that monetize private information, this might seem like a quaint 
idea, but as much as possible, please do not use this data to harm people. 

We cannot make you follow these rules, and anyone can go directly to regulations.gov and download this data directly, 
but we emplor you to use your best judgement when using this data. 

### S3 download costs

The authors of Mirrulations cannot afford to subsidize the download of regulation data. Therefore, Mirrulations is published using 
the [Requestor Pays Bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RequesterPaysBuckets.html) feature of Amazon AWS S3 product. 

If you download the S3 bucket in its entiretly this will result in an Amazon AWS bill of several hundreds of dollars. Even downloading just the text portion can be expensive. To save costs, please download only the portions of the text corpus that you need. 




