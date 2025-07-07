import os
import json

import time
from src.lib_clean.lib_common import my_app_start_time, get_cache_path

print(f"loading module name: {__name__} {time.time() - my_app_start_time}")
my_app_start_time = time.time()

translations_cache_filename_name = r'gcp_translation_cache.json'

translations_cache_filename = get_cache_path(translations_cache_filename_name)

# Load the translation cache if it exists
if os.path.exists(translations_cache_filename):
    with open(translations_cache_filename, 'r', encoding='utf-8') as file:
        translations_cache = json.load(file)
        print(f"translations_cache {translations_cache_filename} size:", len(translations_cache))
else:
    print(" no translations_cache_filename", translations_cache_filename)
    translations_cache = {}

def save_translation_cache():
    print("save_translation_cache()...")
    with open(translations_cache_filename, 'w', encoding='utf-8') as file:
        json.dump(translations_cache, file, indent=1)
    print("save_translation_cache(): done")
