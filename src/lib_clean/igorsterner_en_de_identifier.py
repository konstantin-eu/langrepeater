from transformers import pipeline, AutoConfig

from src.lib_clean.process_language_segments import process_language_segments

model_name = "igorsterner/german-english-code-switching-identification"

# Load model configuration to check labels (optional, for understanding)
# config = AutoConfig.from_pretrained(model_name)
# print(f"Model labels (id2label): {config.id2label}")

# Initialize the token classification pipeline
# Using aggregation_strategy="none" to output each token individually.
nlp = None
try:
    nlp = pipeline(
        "token-classification",
        model=model_name,
        tokenizer=model_name,  # Explicitly providing the tokenizer
        aggregation_strategy="none"  # Changed as per the approach in test1.py
    )
except Exception as e:
    print(f"Error initializing pipeline: {e}")
    print("Make sure you have an internet connection to download the model for the first time.")
    print("And that 'torch' or 'tensorflow' is installed.")
    exit(1)


def identify_language_sections_v2(text: str):
    """
    Identifies sections of a text and their corresponding language using the
    igorsterner/german-english-code-switching-identification model with aggregation_strategy="none".

    Args:
        text: The input string with mixed German and English.

    Returns:
        A list of dictionaries, where each dictionary represents a
        language section and has the following keys:
        - 'text': The text content of the section.
        - 'language': The identified language (e.g., 'GER', 'ENG', 'MIXED', 'NE', 'OTH').
        - 'start': The start character offset of the section in the original text.
        - 'end': The end character offset of the section in the original text.
    """
    # if "Plural" in text:
    #     print("b")

    if not text.strip():
        return []

    # Get classified tokens from the pipeline.
    # With aggregation_strategy="none", each item is a single token.
    # Each token is a dict with 'entity', 'score', 'word', 'start', 'end', 'index'.
    classified_tokens = nlp(text)

    result_segments = []
    if not classified_tokens:
        if text != "":
        # if any(char.isalpha() for char in text):
            result_segments.append({
                'text': text,
                'language': "ANY",
                'start': 0,
                'end': len(text) - 1
            })

        return result_segments


    mixed_word = False
    mixed_word_tokens = []

    # Initialize with the first token
    # current_start_char = classified_tokens[0]['start']
    current_start_char = 0
    current_end_char = classified_tokens[0]['end']
    # The key for the language label is 'entity' when aggregation_strategy is "none".
    current_lang = classified_tokens[0]['entity']
    if len(text) > current_end_char and text[current_end_char].isalpha():
        mixed_word = True
        mixed_word_tokens.append(classified_tokens[0])

    # Original debug print placeholder from the prompt - can be un-commented if needed
    # for token_debug in classified_tokens:
    #     print(f"Token: {token_debug['word']}, Start: {token_debug['start']}, End: {token_debug['end']}, Entity: {token_debug['entity']}")


    for i in range(1, len(classified_tokens)):
        token = classified_tokens[i]
        token_lang = token['entity']
        token_start_char = token['start']
        token_end_char = token['end']

        if len(text) > token_end_char and text[token_end_char].isalpha():
            mixed_word = True
            mixed_word_tokens.append(token)
            # print("___ middle break!")
            continue
        elif mixed_word:
            mixed_word_tokens.append(token)

            ft = mixed_word_tokens[0]
            first_lang = ft['entity']
            if all(token['entity'] == first_lang for token in mixed_word_tokens):
                token_lang = first_lang
                token_start_char = ft['start']
                token_end_char = mixed_word_tokens[- 1]['end']
            else:
                token_lang = "D"
                token_start_char = ft['start']
                token_end_char = mixed_word_tokens[- 1]['end']

            mixed_word = False
            mixed_word_tokens = []

        # raise ValueError("implement!")
        # if len(text) > entity_end and text[entity_end].isalpha():
        #     entity_lang = current_lang

        # Original debug print from the prompt's classificator.py - can be un-commented if needed
        # print(f" ____ processing token: {text[token_start_char:token_end_char]} ({token_lang}) current segment: lang={current_lang} start={current_start_char} end={current_end_char}")

        # If the language is the same as the current segment, extend the segment's end
        if token_lang == current_lang:
            # The `current_end_char` should always be the end of the last token included in the segment.
            # Since tokens can have gaps between them (e.g. spaces), simply setting to token_end_char
            # correctly captures the span of characters that the model considers part of this segment.
            current_end_char = token_end_char
        else:
            # Language changed, so save the current segment.
            # The text for this segment is from `current_start_char` to `current_end_char`
            # (which holds the end of the *previous* token).
            current_end_char = token_start_char
            segment_text = text[current_start_char:current_end_char]
            result_segments.append({
                'text': segment_text,
                'language': current_lang,
                'start': current_start_char,
                'end': current_end_char
            })

            # Start a new segment with the current token's properties
            current_start_char = token_start_char
            current_end_char = token_end_char
            current_lang = token_lang

            # The `is_special_punctuation` logic from the original prompt remains inactive
            # as it was within an `if False:` block and test1.py implies no such special handling.
            if False:  # Kept from original prompt, inactive
                def is_special_punctuation(s, index):  # Definition would be here or global
                    if 0 <= index < len(s):
                        return s[index] in {'!', '?', '.', ':'}
                    return False

                if is_special_punctuation(text, current_end_char):  # Example usage
                    current_end_char += 1  # This type of logic is not active

    # Add the last segment after the loop
    # This segment runs from current_start_char to current_end_char (end of the last token processed)
    if classified_tokens:  # Ensure there was at least one token to process
        segment_text = text[current_start_char:]
        result_segments.append({
            'text': segment_text,
            'language': current_lang,
            'start': current_start_char,
            'end': len(text) - 1
        })

    # The `is_special_punctuation` logic for the last segment from the original prompt remains inactive.
    if False:  # Kept from original prompt, inactive
        # ... (similar special punctuation logic for the very last segment) ...
        pass

    result_segments = process_language_segments(result_segments)

    return result_segments


if __name__ == '__main__':
    # Example Usage
    mixed_text1 = "Das ist ein Satz with some English words, like 'cool' and \"amazing\"!"
    mixed_text2 = "Another example: Was ist das? This is a pen. Und eine 'Quote'."
    mixed_text3 = "Nur Deutsch."
    mixed_text4 = "Only English."
    mixed_text5 = "Short one. Ein kurzer."
    mixed_text6 = "Sentence with punctuation at the end. Satz mit Punkt am Ende."
    mixed_text7 = "\"Ein Zitat am Anfang\", followed by English text."
    mixed_text8 = "Ein Wort: EnglishWord, dann wieder Deutsch."

    texts_to_test = [
        # "Example: Der Thermostat zeichnet die Temperaturänderungen auf. (The thermostat records the temperature changes.) 123",
        # "\"Das Restaurant ist bekannt für seine bodenständigen Gerichte.\" (The restaurant is known for its traditional/local dishes.) - Plural accusative after possessive pronoun",
        "2.  **Plural (`Herausforderungen`):**"
        # mixed_text1,
        # mixed_text2,
        # mixed_text3,
        # mixed_text4,
        # mixed_text5,
        # mixed_text6,
        # mixed_text7,
        # mixed_text8,
        # "Hallo Welt! This is a 'test' with numbers 123 and symbols $%/.",
        # "What about abbreviations like 'e.g.' or Dr. Müller?",
        # "EinTestWortOhneLeerzeichenUndDann EnglishWordThenGerman.",
        # "  Leading spaces. Trailing spaces.  "
    ]

    for i, example_text in enumerate(texts_to_test):
        print(f"\n--- Analyzing Text {i + 1} ---")
        print(f"Original: \"{example_text}\"")
        sections = identify_language_sections_v2(example_text)
        if sections:
            print("Identified Sections:")
            for section in sections:
                print(
                    f"  Start: {section['start']:<3}, End: {section['end']:<3}, "
                    f"Lang: {section['language']:<5}, Text: \"{section['text']}\""
                )
        else:
            print("No sections identified or error occurred (or empty input).")

    # Example with specific model labels for clarity
    config = AutoConfig.from_pretrained("igorsterner/german-english-code-switching-identification")
    print(f"\n--- Model Label Information ---")
    print(f"The model 'igorsterner/german-english-code-switching-identification' uses the following labels:")
    print(f"id2label mapping: {config.id2label}")
    print("Where:")
    print("  ENG: English")
    print("  GER: German")
    print("  MIXED: Intra-word code-switching (e.g., a word composed of morphemes from both languages)")
    print("  NE: Named Entities (language ambiguous or not specific)")
    print("  OTH: Other languages or ambiguous tokens/punctuation not clearly belonging to GER/ENG")