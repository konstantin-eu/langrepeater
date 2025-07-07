check_needed_flag = False

import time
my_app_start_time = time.time()

print(f"loading module name: {__name__} {time.time() - my_app_start_time}")
my_app_start_time = time.time()

from pathlib import Path
import json
import os

def get_app_dir() -> Path:
    base_dir = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    cache_dir = base_dir / "langrepeater"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def get_app_whisper_dir() -> Path:
    return get_app_dir() / "whisper"

def get_app_wav_dir() -> Path:
    return get_app_whisper_dir() / "wav"

def get_cache_path(filename: str = "cache.json") -> Path:
    cache_dir = get_app_dir()
    return cache_dir / filename

def check_needed():
    global check_needed_flag
    check_needed_flag = True

def is_check_needed():
    return check_needed_flag


# split a string into tokens that contains only letter from english or german of russia alphabet
def split_string_into_words(string):
    result = []
    current_part = ""
    for char in string:
        if char.isalpha():
            current_part += char
        else:
            if current_part:
                result.append(current_part)
                current_part = ""
    if current_part:
        result.append(current_part)
    return result

if False:
    print(split_string_into_words("1просто тест abcd"))