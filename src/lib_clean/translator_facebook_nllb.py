# NOTE: Requires installation:
# pip install transformers torch sentencepiece sacremoses accelerate
# 'accelerate' helps manage device placement (GPU/CPU) efficiently.

import torch
from transformers import pipeline
import time # To show time context
import json
import os
import atexit # To save cache on exit
import math # For ceiling division for batches

from src.lib_clean.lib_common import get_cache_path

# --- Configuration ---
model_name = "facebook/nllb-200-distilled-600M" # 600 Million parameters, supports 200+ languages
# model_name = "facebook/nllb-200-3.3B"
CACHE_FILE_NAME = "translation_cache_nllb.json"  # File to store translations

CACHE_FILE = get_cache_path(CACHE_FILE_NAME)

# --- Get Current Time ---
current_time_str = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime())
print(f"Script running at: {current_time_str}") # Based on system time

# --- Device Selection ---
# Use GPU if available (CUDA or Apple Silicon MPS), otherwise CPU
if torch.cuda.is_available():
    device = torch.device("cuda")
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")
elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(): # Check if MPS exists before calling is_available()
    device = torch.device("mps")
    print("Using MPS device (Apple Silicon GPU)")
else:
    device = torch.device("cpu")
    print("Using CPU")

# --- Load Translation Pipeline ---
translator = None # Initialize translator
try:
    print(f"\nLoading translation pipeline for model: {model_name}...")
    # This will download the model (approx 2.4GB) if you haven't used it before.
    translator = pipeline(
        "translation",
        model=model_name,
        device=device,
        # We will handle batching manually in sub-batches,
        # but pipeline's internal batching might still offer benefits.
        # You could still set a pipeline-level batch_size if desired,
        # e.g., batch_size=8, which would apply *within* our sub-batches.
    )
    print("Pipeline loaded successfully.")

except Exception as e:
    print(f"Error loading pipeline: {e}")
    print("Please ensure you have installed the required libraries: transformers, torch, sentencepiece, sacremoses, accelerate")
    exit()

# --- NLLB Language Codes with Short Codes for Cache ---
# NLLB uses specific Flores-200 codes. Find the full list here:
# https://github.com/facebookresearch/flores/blob/main/flores200/README.md#languages-in-flores-200
# Added 'short_code' for cache keys
lang_codes = {
    "English": {"nllb_code": "eng_Latn", "short_code": "en"},
    "German": {"nllb_code": "deu_Latn", "short_code": "de"},
    "French": {"nllb_code": "fra_Latn", "short_code": "fr"},
    "Spanish": {"nllb_code": "spa_Latn", "short_code": "es"},
    "Italian": {"nllb_code": "ita_Latn", "short_code": "it"},
    "Japanese": {"nllb_code": "jpn_Jpan", "short_code": "ja"},
    "Chinese (Simplified)": {"nllb_code": "zho_Hans", "short_code": "zh"},
    "Arabic": {"nllb_code": "arb_Arab", "short_code": "ar"},
    "Hindi": {"nllb_code": "hin_Deva", "short_code": "hi"},
    "Russian": {"nllb_code": "rus_Cyrl", "short_code": "ru"},
}

# --- Cache Handling ---
def load_cache(filename=CACHE_FILE):
    """Loads the translation cache from a JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                print(f"Loading cache from {filename}...")
                cache_data = json.load(f)
                print(f"Cache loaded with {len(cache_data)} entries.")
                return cache_data
        except json.JSONDecodeError:
            print(f"Warning: Cache file {filename} is corrupted. Starting with an empty cache.")
            return {}
        except Exception as e:
            print(f"Warning: Could not load cache file {filename}. Error: {e}. Starting with an empty cache.")
            return {}
    else:
        print("Cache file not found. Starting with an empty cache.")
        return {}

def save_cache(cache_data, filename=CACHE_FILE):
    """Saves the translation cache to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
        # print(f"Cache saved successfully to {filename} with {len(cache_data)} entries.")
    except Exception as e:
        print(f"Error saving cache to {filename}: {e}")

# Load cache at startup
translation_cache = load_cache()

# Register save_cache to be called on script exit
atexit.register(save_cache, translation_cache, CACHE_FILE)


# --- NEW: Function to get a specific cached translation ---
def get_cached_translation(
    text_key: str,
    specification: str,
    cache: dict = translation_cache
) -> str | None:
    """
    Retrieves a specific translation from the cache.

    Args:
        text_key (str): The original text phrase used as the key in the cache.
        specification (str): The desired translation format ('en_en', 'en_de', 'de_en', 'de_de').
        cache (dict): The cache dictionary to use. Defaults to the global cache.

    Returns:
        str | None: The cached translation string if found, otherwise None.
                    Returns None also if the specification exists but its value is null/None.
    """
    allowed_specifications = {"en_en", "en_de", "de_en", "de_de"}
    if specification not in allowed_specifications:
        # This case should ideally be prevented by the calling function's logic
        # print(f"Warning: Invalid specification '{specification}'. Must be one of {allowed_specifications}.")
        return None

    if text_key in cache:
        return cache[text_key].get(specification)
    else:
        return None

# --- Helper to get language details ---
def get_lang_details(lang_name_or_code):
    """Helper to get NLLB code and short code from name or short code."""
    for name, details in lang_codes.items():
        if name == lang_name_or_code or details["short_code"] == lang_name_or_code:
            return details["nllb_code"], details["short_code"]
    raise ValueError(f"Language '{lang_name_or_code}' not found in lang_codes configuration.")


# --- Combined Translation Function (Handles Single & Batch, with Caching & Sub-batching) ---
def translate_nllb(
    texts: list[str] | str,
    source_lang: str,
    target_lang: str,
    sub_batch_size: int = 100, # <--- New parameter for sub-batch size
    cache: dict = translation_cache,
    translator_pipeline=translator
):
    """
    Translates a single text or a batch of texts using the NLLB pipeline,
    processing in sub-batches, with caching support FOR en/de pairs.

    Args:
        texts (list[str] | str): A single text string or a list of text strings.
        source_lang (str): Source language name (e.g., "English") or short code (e.g., "en").
        target_lang (str): Target language name (e.g., "German") or short code (e.g., "de").
        sub_batch_size (int): The maximum number of items to process in each sub-batch call
                              to the translation pipeline. Defaults to 50.
        cache (dict): The dictionary used for caching.
        translator_pipeline: The loaded Hugging Face pipeline.

    Returns:
        list[str] | str: A single translated string or a list of translated strings,
                         corresponding to the input format. Returns "Error..." on failure.
    """
    if not translator_pipeline:
        error_msg = "Error: Pipeline not loaded."
        # Determine return type based on input `texts` type hint, even if it's not a list at runtime yet
        is_list_input_hint = hasattr(texts, '__origin__') and texts.__origin__ is list
        return [error_msg] * (len(texts) if is_list_input_hint and isinstance(texts, list) else 1) if is_list_input_hint else error_msg


    is_single_input = isinstance(texts, str)
    if is_single_input:
        texts = [texts] # Work with a list internally

    texts = [item for item in texts if item not in (None, '')]

    # Basic validation for list items
    if not all(isinstance(t, str) for t in texts):
         error_msg = "Error: All items in the input list must be strings."
         print("error: " + error_msg)
         exit(1)
         # Handle return type based on original input
         return [error_msg] * len(texts) if not is_single_input else error_msg


    try:
        src_nllb_code, src_short_code = get_lang_details(source_lang)
        tgt_nllb_code, tgt_short_code = get_lang_details(target_lang)
    except ValueError as e:
        error_msg = f"Error: {e}"
        return [error_msg] * len(texts) if not is_single_input else error_msg

    # Only 'en' and 'de' translations are cached per requirement
    cache_key_format = f"{src_short_code}_{tgt_short_code}"
    required_keys = ["en_en", "en_de", "de_en", "de_de"]
    can_cache = cache_key_format in required_keys

    results = [None] * len(texts)
    texts_to_translate_indices = []
    texts_to_translate = []

    # 1. Check cache or identify texts needing translation
    for i, text in enumerate(texts):
        # Input validation already happened, assuming text is a string here
        if can_cache:
            cached_value = get_cached_translation(text, cache_key_format, cache)
            if cached_value is not None:
                results[i] = cached_value
            else:
                # Text is not in cache OR this specific translation is missing
                texts_to_translate_indices.append(i)
                texts_to_translate.append(text)
                # Initialize cache entry if text is entirely new and cachable
                if text not in cache:
                     cache[text] = {key: None for key in required_keys}
        else:
             # If not caching this language pair, always mark for translation
             texts_to_translate_indices.append(i)
             texts_to_translate.append(text)


    # 2. Translate missing texts in sub-batches
    if texts_to_translate:
        num_to_translate = len(texts_to_translate)
        num_sub_batches = math.ceil(num_to_translate / sub_batch_size)
        print(f"\n--- Translating {num_to_translate} items in {num_sub_batches} sub-batches (size={sub_batch_size}) ---")
        print(f"Source: {src_nllb_code} ({source_lang})")
        print(f"Target: {tgt_nllb_code} ({target_lang})")

        total_translation_time = 0
        translation_successful = True # Flag to track if any sub-batch failed

        try:
            # Iterate through texts_to_translate in steps of sub_batch_size
            for i in range(0, num_to_translate, sub_batch_size):
                sub_batch_start_time = time.time()
                start_index = i
                end_index = min(i + sub_batch_size, num_to_translate)
                current_sub_batch_num = (i // sub_batch_size) + 1

                # Get the actual texts and their original indices for this sub-batch
                sub_batch_texts = texts_to_translate[start_index:end_index]
                sub_batch_original_indices = texts_to_translate_indices[start_index:end_index]

                if not sub_batch_texts: # Should not happen with correct range, but safety check
                    continue

                print(f"  Processing sub-batch {current_sub_batch_num}/{num_sub_batches} ({len(sub_batch_texts)} items)...")

                # Call the pipeline for the current sub-batch
                sub_pipeline_results = translator_pipeline(
                    sub_batch_texts,
                    src_lang=src_nllb_code,
                    tgt_lang=tgt_nllb_code
                )

                # 3. Update results and cache for this sub-batch
                for j, result_dict in enumerate(sub_pipeline_results):
                    original_index = sub_batch_original_indices[j] # Original index in the input `texts` list
                    original_text = sub_batch_texts[j]            # The text that was just translated
                    translated_text = result_dict['translation_text']

                    results[original_index] = translated_text # Place result in the correct spot

                    # Update cache only if it's one of the required en/de pairs
                    if can_cache:
                        # Cache entry should exist if we are here, but check just in case
                        if original_text not in cache:
                             cache[original_text] = {key: None for key in required_keys}
                        cache[original_text][cache_key_format] = translated_text
                        # print(f"    Cache updated for item index {original_index}: '{original_text[:30]}...'")

                sub_batch_end_time = time.time()
                sub_batch_duration = sub_batch_end_time - sub_batch_start_time
                total_translation_time += sub_batch_duration
                print(f"  Sub-batch {current_sub_batch_num} finished in {sub_batch_duration:.2f} seconds.")

        except Exception as e:
            print(f"\nAn error occurred during sub-batch translation: {e}")
            print("Assigning error messages to remaining untranslated items for this run.")
            error_msg = f"Error: Translation failed ({e})"
            translation_successful = False
            # Assign error only to items that were supposed to be translated but haven't been set yet
            for idx in texts_to_translate_indices:
                if results[idx] is None:
                     results[idx] = error_msg

        if translation_successful and num_to_translate > 0:
             print(f"--- Total batch translation time: {total_translation_time:.2f} seconds ---")


    # 4. Final check for None values (e.g., if error occurred or cache wasn't hit initially)
    # This loop ensures every position in the results list has a value or an error message.
    for i in range(len(results)):
        if results[i] is None:
            # This could happen if:
            # - Caching is enabled, but the specific translation wasn't found initially (get_cached_translation returned None)
            #   AND it wasn't added to texts_to_translate (shouldn't happen with current logic, but defensively check)
            # - An error occurred during translation before this item was processed.
            original_text = texts[i]
            if can_cache:
                # Double-check cache in case it was populated by a concurrent process or if logic missed it
                final_check = get_cached_translation(original_text, cache_key_format, cache)
                if final_check is not None:
                    results[i] = final_check
                else:
                    # If still None, mark as error specific to this item/format
                    results[i] = f"Error: Translation failed or missing for this item ({cache_key_format})."
            else:
                 # If not cachable and still None, it likely failed during batch or was skipped due to error
                 results[i] = "Error: Translation failed for this item."


    # Return single string if single input, otherwise list
    return results[0] if is_single_input else results


# --- Usage Examples ---
if __name__ == "__main__":
    print("\n--- Running Usage Examples ---")

    # --- Example 1: Single translation (populates cache) ---
    print("\nExample 1: Single English to German")
    text_en1 = "This is the first example sentence."
    translation1 = translate_nllb(text_en1, "English", "German")
    print(f"Original (en): '{text_en1}'")
    print(f"Translation (de): '{translation1}'")

    # --- Example 2: Using get_cached_translation ---
    print("\nExample 2: Retrieve directly from cache")
    cached_de = get_cached_translation(text_en1, "en_de")
    print(f"Get cached '{text_en1}' (en_de): '{cached_de}'")
    cached_en_en = get_cached_translation(text_en1, "en_en")
    print(f"Get cached '{text_en1}' (en_en): {cached_en_en} (Expected None if not translated yet)")
    cached_unknown = get_cached_translation("Non-existent text key", "en_de")
    print(f"Get cached 'Non-existent text key' (en_de): {cached_unknown} (Expected None)")
    cached_invalid_spec = get_cached_translation(text_en1, "fr_en") # uses allowed_specifications check
    print(f"Get cached '{text_en1}' (fr_en): {cached_invalid_spec} (Expected None due to invalid spec)")


    # --- Example 3: Run another translation to populate more cache ---
    print("\nExample 3: Translate en -> en to populate cache")
    translate_nllb(text_en1, "en", "en") # Run the translation
    cached_en_en_after = get_cached_translation(text_en1, "en_en") # Retrieve again
    print(f"Get cached '{text_en1}' (en_en) after translation: '{cached_en_en_after}'")

    # --- Example 4: Batch translation with sub-batching (e.g., size 2) ---
    print("\nExample 4: Batch English to German with sub_batch_size=2")
    texts_en_batch = [
        # "This is the first example sentence.", # Should be cached (en_de)
        # "Here is a second sentence for the batch.",
        # "And a third one to make it interesting.",
        # "A fourth sentence to ensure multiple batches.",
        # "Finally, the fifth sentence.",
        "Kann sein, aber nicht muss sein. Die Wolken sehen nicht so bedrohlich aus.",
        "Kann sein, aber nicht muss sein.", "Die Wolken sehen nicht so bedrohlich aus."
    ]
    # Use a small sub_batch_size to demonstrate the looping
    translations_de_batch = translate_nllb(texts_en_batch, "German", "English", sub_batch_size=2)

    print("\nBatch Results (en -> de):")
    for i, (original, translated) in enumerate(zip(texts_en_batch, translations_de_batch)):
        print(f"Item {i+1}:")
        print(f"  Original:   '{original}'")
        print(f"  Translated: '{translated}'")
        # Use get_cached_translation to verify it's in cache now
        verify_cache = get_cached_translation(original, "en_de")
        print(f"  Cache check (en_de): {'Found' if verify_cache else 'Not Found'}")
        print("-" * 10)

    exit(0)

    # --- Example 5: Batch translation with non-cached language ---
    print("\nExample 5: Batch English to French (not cached, sub_batch_size=3)")
    texts_en_batch_fr = [
        "Hello, how are you today?",
        "This translation will not be cached.",
        "Let's test the sub-batching again.",
        "One more sentence.",
    ]
    translations_fr_batch = translate_nllb(texts_en_batch_fr, "en", "fr", sub_batch_size=3)
    print("\nBatch Results (en -> fr):")
    for i, (original, translated) in enumerate(zip(texts_en_batch_fr, translations_fr_batch)):
        print(f"Item {i+1}:")
        print(f"  Original:   '{original}'")
        print(f"  Translated: '{translated}'")
        # Verify it's NOT cached (assuming fr isn't added to caching logic)
        verify_cache = get_cached_translation(original, "en_fr") # This spec is invalid for get_cached_translation
        print(f"  Cache check (en_fr): {'Not Found (or invalid spec)' if verify_cache is None else 'Found (Error!)'}")
        print("-" * 10)

    print("\n--- End of Examples ---")
    print(f"Cache currently contains {len(translation_cache)} entries.")
    # The cache will be saved automatically on exit by atexit