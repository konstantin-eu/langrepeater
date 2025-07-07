import time
import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

import logging

try:
    # Assuming your cache structure is: { source_text: { target_lang_code: translated_text } }
    from src.lib_clean.lib_do_translate_cache import translations_cache
    print("Successfully imported shared translations_cache.")
except ImportError:
    print("Warning: Could not import translations_cache. Using a local dummy dictionary.")
    # Define the cache structure: dict[source_text, dict[target_lang, translation]]
    translations_cache: dict[str, dict[str, str]] = {}

START_TIME = time.time()
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[init] Using device: {device}")

# Using the multilingual MADLAD-400 model
MODEL_NAME = "jbochi/madlad400-3b-mt"
print(f"[init] Loading {MODEL_NAME} …")

# Load in half‑precision (float16) to save memory and potentially speed up GPU inference
tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME)
model = (
    T5ForConditionalGeneration
    .from_pretrained(MODEL_NAME, torch_dtype=torch.float16)
    .to(device)
    .eval() # Set model to evaluation mode (disables dropout, etc.)
)
print(f"[init] Model ready in {time.time() - START_TIME:.1f}s – fp16 on {device}")

# -----------------------------------------------------------------------------
# HELPER – the actual batch pass through the network (private)
# -----------------------------------------------------------------------------
@torch.no_grad() # Disable gradient calculations for inference
def _translate_batch_internal(batch_texts_with_prefix: list[str], max_length: int = 512) -> list[str]:
    """Internal helper that assumes *all* texts need translation and are *already*
       prefixed with the target language token (e.g., '<2en> text')."""
    # print("texts going to model: ", batch_texts_with_prefix) # Debugging

    # Tokenize, pad & truncate on the GPU in a single call
    inputs = tokenizer(
        batch_texts_with_prefix,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_length # Max input tokens, might need adjustment
    ).to(device)

    # Autocast enables mixed-precision inference on GPUs that support it
    with torch.cuda.amp.autocast(enabled=(device=="cuda")):
        generated_ids = model.generate(
            **inputs,
            max_length=max_length + 50, # Allow generated output to be slightly longer
            # num_beams=4,             # Uncomment for better quality / slower generation
            # early_stopping=True,     # Uncomment if using beam search
        )

    # Decode the generated token IDs back to strings
    return tokenizer.batch_decode(generated_ids, skip_special_tokens=True)

# -----------------------------------------------------------------------------
# PUBLIC – high‑level batch translator with multi-language cache
# -----------------------------------------------------------------------------

def translate_batch(
    source_texts: list[str],
    target_lang: str, *,
    batch_size: int = 10,
    max_length: int = 512
) -> list[str]:
    """Translate a batch of texts to the specified target language efficiently on‑GPU.

    * Uses the MADLAD-400 model via Hugging Face Transformers.
    * Supports multiple target languages (specify via target_lang code like 'en', 'fr', 'es').
    * Runs in true batches (\_translate_batch_internal) to saturate GPU throughput.
    * Respects original order of the input list.
    * Transparently consults / updates an external `translations_cache`.
        The cache structure is expected to be: { source_text: { target_lang: translation } }
    * Silently skips empty / non‑string items in the input (returns "" for those).

    Args:
        source_texts: A list of strings to translate.
        target_lang: The target language code (e.g., 'en', 'de', 'fr', 'es', 'ja').
                     Must be a language supported by the model and use the <2xx> format.
        batch_size: How many sentences to process in one GPU pass. Adjust based on VRAM.
        max_length: Maximum token length for input and influences output length.

    Returns:
        A list of translated strings, aligned 1‑to‑1 with the input `source_texts`.
        Untranslatable inputs (e.g., empty strings) result in "" at the corresponding index.
    """
    if not isinstance(source_texts, list):
        raise TypeError("Input 'source_texts' must be a list of strings")
    if not target_lang or not isinstance(target_lang, str):
        raise ValueError("Input 'target_lang' must be a non-empty string (e.g., 'en')")

    # Pre‑allocate output list to maintain order
    output_translations: list[str | None] = [None] * len(source_texts)

    # Buffers for texts that miss the cache and need translation
    pending_indices: list[int] = []
    pending_payload_with_prefix: list[str] = [] # Texts prefixed with <2lang>

    def flush_pending_batch():
        """Process the current batch of pending texts."""
        if not pending_payload_with_prefix:
            return

        print("pending_payload_with_prefix: ", pending_payload_with_prefix)

        # Perform the actual translation on the accumulated batch
        translated_texts = _translate_batch_internal(
            pending_payload_with_prefix,
            max_length=max_length
        )

        print("translated_texts: ", translated_texts)

        # Update the main output list and the cache
        for i, original_list_index in enumerate(pending_indices):
            source_text = source_texts[original_list_index] # Get original text
            translated_text = translated_texts[i]           # Get newly translated text

            output_translations[original_list_index] = translated_text

            # --- Cache Update Logic ---
            # Ensure the source text has an entry in the cache
            if source_text not in translations_cache:
                translations_cache[source_text] = {}
            # Add/update the translation for the *specific target language*
            translations_cache[source_text][target_lang] = translated_text
            # --- End Cache Update ---

        # Clear buffers for the next batch
        pending_indices.clear()
        pending_payload_with_prefix.clear()

    # --- Main Loop ---
    # Iterate through input texts, check cache, and accumulate batches
    for i, text in enumerate(source_texts):
        # Handle invalid inputs gracefully
        if not isinstance(text, str) or not text.strip():
            output_translations[i] = "" # Keep alignment, return empty for invalid input
            continue

        # --- Cache Check ---
        # Look for source_text -> target_lang entry
        cached_translation = translations_cache.get(text, {}).get(target_lang)
        # --- End Cache Check ---

        if cached_translation is not None: # Cache Hit!
            output_translations[i] = cached_translation
            # print(f"Cache hit for: '{text}' -> '{target_lang}'") # Debugging
        else: # Cache Miss
            # Queue this text for translation
            pending_indices.append(i)
            # Add the required prefix for the model
            pending_payload_with_prefix.append(f"<2{target_lang}> {text}")

            # If the batch buffer is full, process it
            if len(pending_payload_with_prefix) >= batch_size:
                # print(f"Flushing batch of size {len(pending_payload_with_prefix)}...") # Debugging
                flush_pending_batch()

    # Process any remaining texts that didn't fill a full batch
    # print(f"Flushing final batch of size {len(pending_payload_with_prefix)}...") # Debugging
    flush_pending_batch()

    # Final check: ensure all placeholders have been filled
    if any(item is None for item in output_translations):
         # This should not happen if logic is correct
         raise RuntimeError("Processing failed: some items were not translated or retrieved from cache.")

    # Cast is safe because we replaced all None values
    return output_translations # type: ignore

# -----------------------------------------------------------------------------
# CONVENIENCE – single‑sentence wrapper
# -----------------------------------------------------------------------------

def translate_single(text: str, target_lang: str) -> str:
    """Translates a single string using the batch processing function."""
    if not isinstance(text, str):
         # Or handle as desired, e.g., return ""
        raise TypeError("Input 'text' must be a string")
    if not text.strip():
        return "" # Return empty if input is empty/whitespace

    # Translate as a batch of one
    result_list = translate_batch([text], target_lang=target_lang, batch_size=1)
    return result_list[0]


# -----------------------------------------------------------------------------
# EXAMPLE USAGE / CLI TEST HARNESS
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("-" * 40)
    print("Starting translation demo...")
    print("Initial cache state:", translations_cache)
    print("-" * 40)

    demo_texts_de = [
        "Guten Morgen! Wie geht es Ihnen heute?",
        "Das Wetter ist heute schön.",
        "Ich würde gerne eine Tasse Kaffee trinken.",
        "Ein kurzer Satz.",
        "", # Empty string
        "Das Wetter ist heute schön.",  # Duplicate to test caching
        "Dieser Satz ist neu und nicht im Cache.",
        None, # Invalid input type
        "    ", # Whitespace only
    ]

    # --- First Pass: German to English ---
    print("\n--- Pass 1: German to English ---")
    t0 = time.time()
    translations_en = translate_batch(demo_texts_de, "en", batch_size=4)
    dt = time.time() - t0
    print(f"Translated {len(demo_texts_de)} items to English in {dt:.2f}s")
    for i, (de, en) in enumerate(zip(demo_texts_de, translations_en)):
        print(f"  [{i}] DE: {de}\n      EN: {en}")
    print("Cache state after EN pass:", translations_cache)

    # --- Second Pass: German to English (should be mostly cached) ---
    print("\n--- Pass 2: German to English (Cache Check) ---")
    t0 = time.time()
    translations_en_cached = translate_batch(demo_texts_de, "en", batch_size=4)
    dt = time.time() - t0
    print(f"Second EN pass took {dt:.4f}s")
    # Optional: Verify results match
    # assert translations_en == translations_en_cached
    print("Cache state:", translations_cache) # Should be unchanged

    # --- Third Pass: German to French (demonstrates multi-language cache) ---
    print("\n--- Pass 3: German to French ---")
    t0 = time.time()
    translations_fr = translate_batch(demo_texts_de, "fr", batch_size=4)
    dt = time.time() - t0
    print(f"Translated {len(demo_texts_de)} items to French in {dt:.2f}s")
    for i, (de, fr) in enumerate(zip(demo_texts_de, translations_fr)):
        print(f"  [{i}] DE: {de}\n      FR: {fr}")
    print("Cache state after FR pass:", translations_cache) # Should now contain 'en' and 'fr' entries

    # --- Fourth Pass: German to French (should be mostly cached) ---
    print("\n--- Pass 4: German to French (Cache Check) ---")
    t0 = time.time()
    translations_fr_cached = translate_batch(demo_texts_de, "fr", batch_size=4)
    dt = time.time() - t0
    print(f"Second FR pass took {dt:.4f}s")
    # Optional: Verify results match
    # assert translations_fr == translations_fr_cached
    print("Cache state:", translations_cache) # Should be unchanged

    # --- Single Translation Example ---
    print("\n--- Single Translation Examples ---")
    single_de = "Hallo Welt"
    print(f"DE: {single_de}")
    single_en = translate_single(single_de, "en")
    print(f"EN: {single_en}")
    single_es = translate_single(single_de, "es") # Spanish
    print(f"ES: {single_es}")
    # Try retrieving the English one again (should be cached)
    t0 = time.time()
    single_en_cached = translate_single(single_de, "en")
    print(f"EN (cached): {single_en_cached} (retrieved in {time.time() - t0:.5f}s)")
    print("Final cache state:", translations_cache)

    print("-" * 40)
    print("Translation demo finished.")
    print("-" * 40)