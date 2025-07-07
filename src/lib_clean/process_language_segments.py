def process_language_segments(segments, dominance_threshold=0.8):
    """
    Process a list of text segments and handle language dominance.

    Args:
        segments: List of dicts with 'text' and 'language' keys
        dominance_threshold: Threshold for determining language dominance (default: 0.8 = 80%)

    Returns:
        Updated list with minority language entries converted to dominant language

    Raises:
        ValueError: If more than 2 languages are present
    """
    if not segments:
        return segments

    # Step 1: Aggregate text lengths by language
    language_lengths = {}
    for segment in segments:
        lang = segment['language']
        text_length = len(segment['text'])
        language_lengths[lang] = language_lengths.get(lang, 0) + text_length

    # Step 2: Check if more than 2 languages
    if len(language_lengths) > 2:
        raise ValueError(f"More than 2 languages found: {list(language_lengths.keys())} segments:{segments}")

    # Step 3: If only one language or no segments, return as-is
    if len(language_lengths) <= 1:
        return segments

    # Step 4: Calculate ratios for exactly 2 languages
    total_length = sum(language_lengths.values())
    language_ratios = {lang: length / total_length for lang, length in language_lengths.items()}

    # Step 5: Check for dominance
    dominant_lang = None
    minority_lang = None

    for lang, ratio in language_ratios.items():
        if ratio >= dominance_threshold and lang == "D":
            dominant_lang = lang
            # Find the minority language
            for other_lang in language_ratios:
                if other_lang != lang:
                    minority_lang = other_lang
            break

    # Step 6: Update list if dominance is found
    if dominant_lang and minority_lang:
        updated_segments = []
        for segment in segments:
            updated_segment = segment.copy()
            if updated_segment['language'] == minority_lang:
                updated_segment['language'] = dominant_lang
            updated_segments.append(updated_segment)
        return updated_segments

    # Step 7: No dominance found, return original list
    return segments


# Example usage:
if __name__ == "__main__":
    # Test data
    test_segments = [
        # {'text': 'Hello world this is a long English text', 'language': 'en'},
        # {'text': 'Another English sentence here', 'language': 'en'},
        # {'text': 'Bonjour', 'language': 'fr'},
        # {'text': 'More English content with substantial length', 'language': 'en'},
        {'text': 'Mein Vorschlag ist, dass ich die Aufgabe übernehme, das Geschenk zu kaufen, und du kümmerst dich um die Musik für die', 'language': 'D'},
        {'text': 'Party.', 'language': 'E'},
        # {'text': 'Mein Vorschlag ist, dass ich die Aufgabe übernehme, das Geschenk zu kaufen, und du kümmerst dich um die Musik für die', 'language': 'D'},
    ]
    # Mein Vorschlag ist, dass ich die Aufgabe übernehme, das Geschenk zu kaufen, und du kümmerst dich um die Musik für die ', 'language': 'D', 'start': 0, 'end': 118}, {'text': 'Party.', 'language': 'E', 'start': 118, 'end': 123

    try:
        result = process_language_segments(test_segments)
        print("Original segments:")
        for i, seg in enumerate(test_segments):
            print(f"  {i}: '{seg['text'][:30]}...' -> {seg['language']}")

        print("\nUpdated segments:")
        for i, seg in enumerate(result):
            print(f"  {i}: '{seg['text'][:30]}...' -> {seg['language']}")

    except ValueError as e:
        print(f"Error: {e}")