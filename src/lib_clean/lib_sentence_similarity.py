import time
from src.lib_clean.lib_common import my_app_start_time, get_cache_path

print(f"loading module name: {__name__} {time.time() - my_app_start_time}")
my_app_start_time = time.time()

import json
import os
from sentence_transformers import SentenceTransformer, util

# Load model globally only once
# model = SentenceTransformer('all-mpnet-base-v2')

# sentence-transformers/all-MiniLM-L6-v2
model = SentenceTransformer('all-MiniLM-L6-v2')


use_cache = True
cache_file_name= 'scores_cache.json'

import json

def load_scores_cache():
    """
    Load scores (phrase1||phrase2 => score) from a JSON cache file.
    If the file doesn't exist, return an empty dict.
    """

    cache_file = get_cache_path(cache_file_name)
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            scores_cache = json.load(f)
            print(f"scores_cache {cache_file}", len(scores_cache))
            return scores_cache
    else:
        print(" no scores_cache cache_file", cache_file)
        # exit(1)
    return {}

if use_cache:
    # Load existing cache (dictionary) { "phrase1||phrase2": score }
    scores_cache = load_scores_cache()

def save_scores_cache():
    if not use_cache:
        return

    """
    Save the current scores cache to a JSON file.
    """
    print("save_scores_cache()...")
    cache_file = get_cache_path(cache_file_name)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(scores_cache, f, ensure_ascii=False, indent=2)
    print("save_scores_cache(). done")


def compare_sentences(phrase1, phrase2):
    """
    Compare two English phrases and return a similarity score (0 to 1) using 'all-mpnet-base-v2'.
    Scores are stored in a JSON file so that identical comparisons do not need to be recalculated.

    :param phrase1: First phrase as a string.
    :param phrase2: Second phrase as a string.
    :param cache_file: Filename for the JSON cache.
    :return: Similarity score (float) between 0 and 1.
    """

    if phrase1 == "" or phrase2 == "":
        return 0.0

    if phrase1 == phrase2:
        print("strings equal!")
        return 1.0

    # Generate a unique key for the pair
    key = phrase1 + "||" + phrase2

    if use_cache:
        # If this pair was already computed, return cached value
        if key in scores_cache:
            return scores_cache[key]

    # Otherwise, compute the similarity
    embedding1 = model.encode(phrase1, convert_to_tensor=True)
    embedding2 = model.encode(phrase2, convert_to_tensor=True)
    similarity = util.cos_sim(embedding1, embedding2).item()

    if use_cache:
        # Store the new score in the cache
        scores_cache[key] = similarity


    return similarity


# Example usage
if False:
    s1 = "How to tie a tie?"
    s2 = "Ways to knot a necktie."
    s1 = "He carried the heavy stone with his bare hands."
    s2 = ".He carried the heavy stone with bare hands."
    score = compare_sentences(s1, s2)
    print(f"Similarity Score: {score:.4f}")
    save_scores_cache()

if False:
    # Example usage
    phrase1 = "aufzeichnen often implies creating a visual mark, graph, log, or data record. aufnehmen has a broader sense of."
    phrase2 = "Unter Aufzeichnen versteht man häufig das Erstellen einer visuellen Markierung, eines Diagramms, eines Protokolls oder eines Datensatzes. Der Begriff Aufzeichnen hat eine breitere Bedeutung."
    score = compare_sentences(phrase1, phrase2)
    print(f"Similarity score: {score}")

# batch comparison
if False:
    sentences = [
        # "The cat sat on the mat.",
        # "A feline was resting on the carpet.",
        # "The dog chased the ball."

    "I went to the cinema for free yesterday. My brother invited me.",

    "I was at the movies for free yesterday. My brother invited me."
    ]

    #Compute embeddings
    embeddings = model.encode(sentences, convert_to_tensor=True)

    def compare_sentences_batch():
        #Compute cosine-similarities
        cosine_scores = util.cos_sim(embeddings, embeddings)

    if True:
        #Output the pairs with their score
        for i in range(len(sentences)):
            for j in range(i+1, len(sentences)):
                print("{} \t\t {} \t\t Score: {:.4f}".format(sentences[i], sentences[j], cosine_scores[i][j]))