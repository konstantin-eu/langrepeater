import spacy

# break text into sentences model
# pip install spacy
# python -m spacy download de_core_news_sm

# Load the German NLP model
nlp = spacy.load("de_core_news_sm")

nlp_en = spacy.load("de_core_news_sm")

def break_de_text_to_sentences(text):
    # Process the text
    doc = nlp(text)

    # Extract sentences
    return [sent.text for sent in doc.sents]

def break_en_text_to_sentences(text):
    # Process the text
    doc = nlp_en(text)

    # Extract sentences
    return [sent.text for sent in doc.sents]


if __name__ == "__main__":
    # German text
    text = "Das ist der erste Satz. In Deutschland können Eltern bis zum 14. Lebensjahr ihres Kindes entscheiden, ob es in der Schule am Religionsunterricht teilnimmt. Hier ist ein zweiter Satz! Und noch einer?"

    # Process the text
    doc = nlp(text)

    # Extract sentences
    sentences = [sent.text for sent in doc.sents]

    # Print results
    print(sentences)
