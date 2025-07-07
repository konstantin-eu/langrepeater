from pathlib import Path
from mistletoe import Document, span_token

from src.lib_clean.helper1 import remove_all_non_starting_asterisks_regex
from src.lib_clean.helper1 import capitalize_first_letter_in_text
from src.lib_clean.lib_do_translate_cache import save_translation_cache
from src.lib_clean.lib_gcp_do_translate import translate_de
from src.lib_clean.lr_compiler_srt import filter_strings_with_alnum
from src.lib_clean.spaCy_sentence_breaker import break_de_text_to_sentences, break_en_text_to_sentences
from src.lib_clean.translator_facebook_nllb import translate_nllb
from src.lib_clean.lib_sentence_similarity import compare_sentences, save_scores_cache
from src.lib_clean.igorsterner_en_de_identifier import identify_language_sections_v2


start_newline = False
current_line_number = 0
de_phrase = ""
next_lang = ""

def validate_language(language):
    allowed_languages = {'E', 'D'}
    if language not in allowed_languages:
        raise ValueError(f"Invalid language '{language}'. Allowed values are: {', '.join(allowed_languages)}")

def _node_text(node: object) -> str:
    if isinstance(node, span_token.RawText):
        return node.content           # the actual characters
    return ""                         # List, ListItem, Paragraph, …

min_de_len = 30


def clean_text(line):
    line = line.replace("“", "\"")
    line = line.replace("”", "\"")
    line = line.replace("„", "\"")
    line = line.replace("–", "-")
    line = line.replace("=", "-")
    line = line.replace('’', "'")
    line = line.replace(';', ".")
    line = line.replace('—', "-")
    line = line.replace('…', ".")
    line = line.replace('[', "(")
    line = line.replace(']', ")")
    line = line.replace('\t', ' ')

    # line = remove_emojis(line)

    # special symbols replace like icons and smiles
    line = re.sub(r'[\\>_✕→➡✅😊📌→`➤←]', '', line)
    return line

def out_file_write(out_file, text):
    text = remove_all_non_starting_asterisks_regex(text)

    out_file.write(text)




import re


def fix_contraction_spacing(text):
    """
    Fix spacing before apostrophes in contractions while preserving quoted text.

    Args:
        text (str): Input text with spacing issues

    Returns:
        str: Text with fixed contraction spacing
    """
    # Pattern matches: word + space + apostrophe + common contraction endings
    # This targets contractions specifically and avoids quoted text
    contraction_pattern = r'\b(\w+)\s+\'(ll|m|t|ve|re|s|d)\b'

    # Replace with word + apostrophe + ending (no space)
    fixed_text = re.sub(contraction_pattern, r'\1\'\2', text)

    return fixed_text

def clean_de_translate(text):

    parts = break_de_text_to_sentences(text)
    parts = filter_strings_with_alnum(parts)
    ret_list = [None] * len(parts)
    to_translate = []
    for i, p in enumerate(parts):
        p = capitalize_first_letter_in_text(p)
        p = re.sub(r'\s+', ' ', p).strip()
        word_count = len(p.split())
        if word_count < 2:
            ret_list[i] = fix_contraction_spacing(translate_de(p))
        else:
            to_translate.append(p)


    tr_list_t = translate_nllb(to_translate, "German", "English")
    tr_list = []
    for t in tr_list_t:
        tr_list.append(fix_contraction_spacing(t))

    j = 0
    for i in range(len(ret_list)):
        if not ret_list[i]:
            ret_list[i] = tr_list[j]
            j += 1

    if None in ret_list:
        raise ValueError("none in translation list!")

    result = " ".join(ret_list)

    r = clean_text(result)
    return r

md_file_lines = []
codefence_parent = False
text_line_combined = []
def _walk(pnode, node, out_file, level) -> None:
    global next_lang
    global de_phrase
    global codefence_parent
    global start_newline
    global text_line_combined

    global current_line_number

    text = _node_text(node)

    new_line = -1
    if hasattr(node, 'line_number'):
        new_line = node.line_number
    else:
        if not codefence_parent:
            new_line = search_substring_in_lines(md_file_lines, text.strip(), max(0, current_line_number - 1))
        else:
            new_line = current_line_number

    if new_line != current_line_number:
        if current_line_number >= new_line:
            raise ValueError("line number 3 error!")
        current_line_number = new_line
        # global start_top
        start_newline = True

    saved_start_newline = start_newline
    # """Depth-first traversal that prints each piece of text once."""


    if text:
        start_newline = False

    if text and codefence_parent:
        do_walk(text_line_combined, out_file, False)
        text_line_combined = []
        do_walk([text], out_file, True)
        codefence_parent = False
    elif text and not codefence_parent:                          # skip empty-text containers
        if saved_start_newline:
            do_walk(text_line_combined, out_file, False)
            text_line_combined = [text]
        else:
            text_line_combined.append(text)
    elif saved_start_newline and not codefence_parent and len(text_line_combined) > 0:
        do_walk(text_line_combined, out_file, False)
        text_line_combined = []

    for child in getattr(node, "children", []) or []:
        _walk(node, child, out_file, level + 1)

def normalize_spaces(text):
    return re.sub(r'\s+', ' ', text)

def replace_any_language(entries, lang_to_replace):
    """
    Replace entries with language 'ANY' based on neighboring entries.

    Rules:
    1. If before 'ANY' there is another language, replace 'ANY' with that language
    2. If after 'ANY' there is another language, replace 'ANY' with that language
    3. If there is only one entry with 'ANY', raise an exception

    Args:
        entries: List of dictionaries with 'text' and 'language' keys

    Returns:
        Modified list with 'ANY' languages replaced

    Raises:
        Exception: If there's only one entry and it has language 'ANY'
    """

    # Check if there's only one entry and it has language 'ANY'
    if len(entries) == 1 and entries[0]['language'] == lang_to_replace:
        entries[0]['language'] = "E"
        return entries

    # Create a copy to avoid modifying the original list
    result = entries.copy()

    # Process each entry
    for i, entry in enumerate(result):
        if entry['language'] == lang_to_replace:
            replacement_lang = None

            # First, check if there's a language before
            if i > 0 and result[i - 1]['language'] != lang_to_replace:
                replacement_lang = result[i - 1]['language']

            # If no valid language before, check after
            elif i < len(result) - 1 and result[i + 1]['language'] != lang_to_replace:
                replacement_lang = result[i + 1]['language']

            # Replace the language if we found a valid one
            if replacement_lang:
                entry['language'] = replacement_lang

    return result

def replace_language_based_on_pattern(data_list):
    """
    Replaces the language of an item from 'E' to 'D' if it's part of a 'D, E, D'
    sequence and its text contains only one word.

    Args:
      data_list: A list of dictionaries, where each dictionary has a
                 'language' (string) and 'text' (string) key.

    Returns:
      A new list with the modified language fields.
    """
    if not data_list or len(data_list) < 3:
        return data_list  # Not enough items to form the D, E, D pattern

    new_list = [item.copy() for item in data_list]  # Work on a copy

    for i in range(len(new_list) - 2):
        # Check for the D, E, D pattern
        if (new_list[i]['language'] == 'D' and
                new_list[i + 1]['language'] == 'E' and
                new_list[i + 2]['language'] == 'D'):

            # Check if the 'E' item's text contains only one word
            text_e = new_list[i + 1].get('text', '')  # Default to empty string if no 'text'
            contains_alpha = any(char.isalpha() for char in text_e)
            if len(text_e.split()) == 1 and contains_alpha:
                new_list[i + 1]['language'] = 'D'
    return new_list

def combine_consecutive_entries(entries):
    if not entries:
        return []

    entries = replace_any_language(entries, "ANY")
    entries = replace_any_language(entries, "M")

    combined = [entries[0]]

    for entry in entries[1:]:
        last = combined[-1]
        if entry['language'] == last['language']:
            # Combine texts and adjust the end time
            last['text'] += " " + entry['text']
            last['text'] = normalize_spaces(last['text'])

            last['end'] = entry['end']
        else:
            combined.append(entry)

    return combined

def do_walk(parts_on_same_line, out_file, codefence_parent) -> None:
    global next_lang
    global de_phrase

    if len(parts_on_same_line) > 0 and codefence_parent:
        if next_lang == "E":
            english_translation = clean_de_translate(de_phrase)
            out_file_write(out_file, english_translation + "\n")
            next_lang = ""
            de_phrase = ""
        if len(parts_on_same_line) != 1:
            raise ValueError("wrong size!")
        out_file_write(out_file, parts_on_same_line[0] + "\n")
    elif len(parts_on_same_line) > 0:                          # skip empty-text containers
        sections = []
        for text in parts_on_same_line:
            text = clean_text(text)
            sections_more = identify_language_sections_v2(text)
            sections.extend(sections_more)

        sections = combine_consecutive_entries(sections)

        for item in sections:
            validate_language(item["language"])
            if item["language"] == "D":
                parts = break_de_text_to_sentences(item["text"])
                parts = filter_strings_with_alnum(parts)
                item["text"] = " ".join(parts)
            else:
                parts = break_en_text_to_sentences(item["text"])
                parts = filter_strings_with_alnum(parts)
                item["text"] = " ".join(parts)

        if len(sections) == 1 and sections[0]["language"] == "D" and len(sections[0]["text"]) > min_de_len:
            if next_lang == "E":
                english_translation = clean_de_translate(de_phrase)
                out_file_write(out_file, english_translation + "\n")
            txt = sections[0]["text"]
            out_file_write(out_file, "\n" + txt + "\n")
            de_phrase = txt
            next_lang = "E"
        elif sections:

            add_asterisk = True
            for s in sections:
                s_lang = s["language"]
                validate_language(s_lang)
                s_text = s["text"]
                if s_lang == "D" and next_lang == "E":
                    english_translation = clean_de_translate(de_phrase)
                    out_file_write(out_file, english_translation + "\n")
                    next_lang = ""
                    de_phrase = ""
                    add_asterisk = True

                if next_lang == "E":
                    if de_phrase == "":
                        raise ValueError("wrong!")
                    english_translation = clean_de_translate(de_phrase)

                    similarity_score = compare_sentences(english_translation, s_text)
                    print("similarity_score: ", similarity_score, english_translation, s_text)
                    if similarity_score > 0.85:
                        out_file_write(out_file, s_text + "\n")
                        next_lang = ""
                        de_phrase = ""
                        add_asterisk = True
                        continue
                    else:
                        out_file_write(out_file, english_translation  + "\n")
                    next_lang = ""
                    de_phrase = ""
                    add_asterisk = True

                if True:
                    if add_asterisk:
                        out_file_write(out_file, "* ")

                    if s_lang == "D" and len(s_text) > min_de_len:
                        out_file_write(out_file, "\n" + s_text + "\n")
                        de_phrase = s_text
                        next_lang = "E"
                    else:
                        if s_lang == "D":
                            out_file_write(out_file, "|de:")
                        elif not add_asterisk:
                            out_file_write(out_file, "|")
                        out_file_write(out_file, s_text)
                        next_lang = ""

                        add_asterisk = False

            out_file_write(out_file, "\n")

def read_file_to_list(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    return lines

def search_substring_in_lines(lines, substring, start_index):
    for i in range(start_index, len(lines)):
        if substring in lines[i]:
            return i + 1  # Return the index of the first match
    raise ValueError(f"Not found substring: [{substring}]")

def parse_markdown_file(path: str | Path, out_path) -> None:
    global codefence_parent
    global current_line_number
    global next_lang
    global de_phrase
    global text_line_combined
    global md_file_lines

    md_file_lines = read_file_to_list(path)

    with open(out_path, 'w', encoding='utf-8') as out_file:
        """Read *path*, parse it, and visit every Markdown element."""
        with Path(path).expanduser().open(encoding="utf-8") as md:
            doc = Document(md)
        for top_level in doc.children:
            if not top_level.line_number:
                raise ValueError("line number!")

            if current_line_number >= top_level.line_number:
                raise ValueError("line number 2!")

            if "CodeFence" in str(type(top_level).__name__):
                codefence_parent = True
            _walk(None, top_level, out_file, 1)

        if len(text_line_combined) > 0:
            do_walk(text_line_combined, out_file, codefence_parent)

        if next_lang == "E":
            if de_phrase == "":
                raise ValueError("empty de phrase!")
            english_translation = clean_de_translate(de_phrase)
            out_file_write(out_file, english_translation + "\n")
            next_lang = ""
            de_phrase = ""

        if next_lang != "":
            raise ValueError("translation left!")

    print("completed.")
    save_translation_cache()
    save_scores_cache()





