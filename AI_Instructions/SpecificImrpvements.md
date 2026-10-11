Specific Improvements
===================


* When we store json documents, they should all be pretty-printed for readability. This includes converting the raw downloads. Otherwise it is not possible for a human to browse the data and browsing the data is the whole point of this project. 
* There should be portions of the json associated with every comment that needs to be included at the beginning of every markdown file in the metadata. This includes the title, the authors, the organizattion or persons name. If it is a pdf, the link to the original document should be included as a markdown link like [original pdf](https://downloads.regulations.gov/CMS-2026-1255-0009/attachment_1.pdf)
* At this stage a simple template of metadata should be used to create a "friendly document name for this comment/document" or just "friendly name", which should be included in the document metadata.
* As an artifact of the stage 2 citations work, lets use a quick visit to the LLI site to get the name of the record. For instance "https://www.law.cornell.edu/cfr/text/42/482.24 " would return "42 CFR § 482.24 - Condition of participation: Medical record services." in the html page title. This is what the human readable portion of the anchor text should contain. Once the citation mining is complete there should be two metadata files created: 
* First, a reverse lookup markdown file that would list every citation once, and then have an array of the friendly name of the markdown documents and the paragraph where that legal reference occured
* Second there should be a "friendly name" markdown document which should be a table with four columns, the official_reference_name of the referene, a "friendly_reference_name", which should be the same as the official_reference_name to start, the reference text itself, and the link to the LLI or other resource for the reference. This table should eb manually editable, so that on subsequent runs of the citation system, the friendly_reference_name will be used instead of the official_reference_name. This will allow our citations links to become human grokable over time. Subsequent passes of the citation extraction should not modify existing friendly_reference_names. 
* A similar "friendly_name" persistent human editable system should exist for the documents themselves. This will simple be a three column table in markdown that lists the "generated_friendly_name", the "edited_friendly_name", as well as the local path to the markdown document itself. For later stages where we are making sense-making for these documents: "AGA comments" will be much easier to work with than "AGA comments: the persuasive nature of hospital interoperability policies, given our turbulent meta-billing approaches".

Approved clarifications
-----------------------

* Verify rclone bytes before pretty-printing JSON in place. Record both hashes;
  the normalized source tree is not byte-exact.
* Generate document names from `f"{organization} {person_name}: {title}"`,
  omitting empty components and malformed spacing or punctuation.
* Replace visible citation anchor text with the current friendly reference
  name. Preserve original matched wording in authoritative sidecars.
* Create global `metadata/citation_reverse_lookup.md`,
  `metadata/reference_friendly_names.md`, and
  `metadata/document_friendly_names.md` files.
* Reverse lookup uses one heading per citation and bullet links to friendly
  document names and paragraph anchors.
* Cache title retrieval. On fetch failure, use normalized citation text and
  retry only on explicit refresh.
* Never overwrite existing edited reference or document friendly names.
* Editable friendly-name columns start blank. Use them only when a human has
  entered a nonblank value; otherwise use the official reference name or
  generated document name.
