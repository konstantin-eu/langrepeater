from google.cloud import translate_v2 as translate

from src.lib_clean.lib_do_translate_cache import translations_cache
from src.lib_clean.llm_translate import translate_text_with_model

import time
from src.lib_clean.lib_common import my_app_start_time
print(f"loading module name: {__name__} {time.time() - my_app_start_time}")
my_app_start_time = time.time()

client = translate.Client()

def translate_de(text):
    # Translate a single line by wrapping it in a list
    return translate_de_gcp(text)

# Initialize the Translation client
def translate_de_gcp(text):
    if text in translations_cache:
        return translations_cache[text]['en']

    print(f"GCP Translating DE phrase: {text}")

    if True:
        target_language = "en"

        global client
        # model='general/translation-llm'
        result = client.translate(text, target_language=target_language, source_language='de', format_='text', model='nmt')
        tr = result['translatedText']
    else:
        tr = translate_text_with_model(text)

    translations_cache[text] = {'en': tr}

    return tr
