"""
Initial work to extract all the signatures names from a file
that contains multiple comments.  The process searches for 
a closing phrase (e.g., "Sincerely") and then looks for a
PERSON entity immediately after.

This will work using the en_core_web_sm model, but it only finds ~85% 
of the signatures.  The en_core_web_trf model did better when we ran 
it on a smaller file, but the system runs out of memory when we run it 
on larger files.

One solution would be to break the file into smaller chunks and run
the model on each chunk.  The challenge is that we need to find a
safe way to break the file into chunks that doesn't put the
closing phrase in one chunk and the signature in another.

 """

import spacy
import spacy_transformers
import en_core_web_trf
import re

nlp = nlp = en_core_web_trf.load() #spacy.load("en_core_web_trf")

closing_phrases = ["Sincerely", "Best regards", "Yours faithfully"]

def make_doc(path):
    data = open(path).read().replace('\x0C', '\n.\n')
    clean_data = data #re.sub(r'\s+', ' ', data)
    return nlp(clean_data)

def first_person(sent):
    for ent in sent.ents:
        if ent.label_ == 'PERSON':
            return ent
    return ''

def get_signatures(doc):
    sigs = []
    for sent in doc.sents:
        for phrase in closing_phrases:
            if phrase in sent.text:
                sigs.append(first_person(sent))
                #sigs.append([(ent.text, ent.label_) for ent in sent.ents if ent.label_ == 'PERSON'])
                #sigs.append([(token.text, token.pos_) for token in sent[len(phrase.split()):] if token.pos_ not in ["SPACE", 'PUNCT']])
                #if len(sent.ents) > 0:
                #    sigs.append(sent.ents[0])
                #else:
                #    sigs.append('')
                break
    return sigs

nlp.max_length = 10000000
names = get_signatures(make_doc('../examples/extracted_text/mail_merge/EPA-HQ-OA-2017-0190-33955_attachment_1_extracted.txt'))
#names = get_signatures(make_doc('../examples/extracted_text/mail_merge/EPA-short.txt'))

with open('all_signatures.txt', 'w') as f:
    for name in names:
        f.write(str(name) + '\n')
