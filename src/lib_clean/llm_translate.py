from google.cloud import translate

def translate_text_with_model(
    text: str = "YOUR_TEXT_TO_TRANSLATE",
    project_id: str = "langrepeater",
    model_id: str = "general/translation-llm",
):
    # -&gt; translate.TranslationServiceClient:
    """Translates a given text using Translation custom model."""


    client = translate.TranslationServiceClient()


    location = "us-central1"
    parent = f"projects/{project_id}/locations/{location}"
    model_path = f"{parent}/models/{model_id}"


    # Supported language codes: https://cloud.google.com/translate/docs/languages
    response = client.translate_text(
        request={
            "contents": [text],
            "target_language_code": "en",
            "model": model_path,
            "source_language_code": "de",
            "parent": parent,
            "mime_type": "text/plain",  # mime types: text/plain, text/html
        }
    )
    # Display the translation for each input text provided
    for translation in response.translations:
        print(f"Translated text: {translation.translated_text}")


    return response.translations[0].translated_text

if False:
    t = "Das ist ein test!"

    if not my_project_id:
        raise ValueError("needed GCP my_project_id!")

    t = translate_text_with_model(
        text=t, project_id=my_project_id, model_id="general/translation-llm")

    print("text: ", t)