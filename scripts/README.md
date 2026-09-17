A place to store the various scripts we plan on using

## Setup

- In the root directory (NOT in `scripts`) create a virtual environment

  `python3 -m venv .venv`

- Activate the virtual environment

  `source .venv/bin/activate`

- Install the required libraries

  `pip install -r requirements.txt`

- Edit or create a `.env` file in the root directory (not in `scripts`)

  ```
  DATA_ROOT=<absolute path to data>
  ```

  NOTE: Be sure to use an ABSOLUTE path so you can run scripts directly
  from the `examples` folder.

  NOTE: The `data/` folder is ignored by this repo.

### Spacy Setup

The `spacy` requires you to install a language model. The following will give you a small model for English (run with the virtual environment active):

`python -m spacy download en_core_web_sm`
