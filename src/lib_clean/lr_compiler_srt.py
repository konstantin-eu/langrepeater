import os

from src.lib_clean.spaCy_sentence_breaker import break_de_text_to_sentences

def filter_strings_with_alnum(string_list):
    """
    Filters a list of strings, keeping only elements that contain at least one letter or number.
    """
    filtered_list = []
    for s in string_list:
        # Check if any character in the string is alphanumeric
        if any(char.isalnum() for char in s):
            filtered_list.append(s)
    return filtered_list

def do_lr_compiler_srt_to_lr_txt_format_and_translate(input_file, output_file):

    def addSecond(line):
        start_time, end_time = line.strip().split(' --> ')
        h, m, s = map(float, end_time.replace(',', '.').split(':'))
        total_seconds = h * 3600 + m * 60 + s
        total_seconds += 1
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = total_seconds % 60
        end_time = f"{h:02}:{m:02}:{s:06.3f}".replace('.', ',')
        line = f"{start_time} --> {end_time}"
        return line

    def parse_ts(line, extra_delay_sec):
        if "-->" not in line:
            raise ValueError("cannot happen: ts line: ", line)
        start_time, end_time = line.strip().split(' --> ')
        h, m, s = map(float, end_time.replace(',', '.').split(':'))
        total_seconds = h * 3600 + m * 60 + s
        total_seconds += extra_delay_sec
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = total_seconds % 60
        end_time = f"{h:02}:{m:02}:{s:06.3f}".replace('.', ',')
        return start_time, end_time

    def render_ts(start_time, end_time):
        line = f"{start_time} --> {end_time}"
        return line

    def extract_file_parts(file_path):
        # Extract directory
        directory = os.path.dirname(file_path)
        # Extract filename with extension
        filename_with_extension = os.path.basename(file_path)
        # Split into filename without extension and extension
        filename, extension = os.path.splitext(filename_with_extension)

        return directory, filename, extension

    doAddSecond = True

    do_break_into_sentences = False
    gcp_translate = False
    directory, filename, extension = extract_file_parts(input_file)
    orig_file_name = filename + '.wav'
    orig_file_name_cleaned = orig_file_name.replace("_word_merge", "")
    print(orig_file_name_cleaned)

    output_file_srt_translated = directory + "\\" + filename + '_translated.srt'
    option_extra_delay_sec = 0  # looks like no needed check shift_sentence_end_sec_extra
    # option_extra_delay_sec = 2  # looks like no needed check shift_sentence_end_sec_extra

    with open(input_file, 'r', encoding='utf-8') as infile:
        lines = infile.readlines()

    # We'll store the lines that need translation
    german_lines_to_translate = []
    german_lines_positions = []

    i = 0
    lines_preprocessed = []
    while i < len(lines):
        line = lines[i]
        if i == 0:
            line = line.replace(u'\ufeff', '')  # remove BOM if present

        if line.strip() == "":
            i += 1
            continue

        if line.strip().isdigit():
            # lines_preprocessed.append(line)
            i += 1
            continue
        elif '-->' in line.strip():
            lines_preprocessed.append(line)
            i += 1
            continue

        else:
        # If the next line is not a digit or empty, it might be a continuation of the sentence
            if i + 1 < len(lines) and (
                    lines[i + 1].strip() != "" and not lines[i + 1].strip().isdigit() and '-->' not in lines[i + 1]):
                # Combine current and next line
                line = line.strip() + " " + lines[i + 1].strip()
                i += 1

            # We now have a German line to translate
            original_german = line.strip()
            lines_preprocessed.append(line)
            i += 1

    # state machine
    s_init = "s_init"
    s_ts = "s_ts"
    s_de_start = "s_de_start"
    s_de_end = "s_de_end"

    ############## state machine state begin ##############
    ts1 = ""
    ts2 = ""
    sentence = ""

    state = s_init
    ############## state machine state end ##############

    def build_ts(ts1, ts2):
        # if ts1 == ts2:
        #     return ts1.strip() + " " + orig_file_name

        if "-->" not in ts1:
            raise ValueError("cannot happen: ts1 line: ", ts1)
        if "-->" not in ts2:
            raise ValueError("cannot happen: ts2 line: ", ts2)
        t1, _ = parse_ts(ts1, 0)
        _, t4 = parse_ts(ts2, option_extra_delay_sec)
        return render_ts(t1, t4)

    def sm_process(line, next_line, lines_sentences):
        global state
        global ts1
        global ts2
        global sentence

        if line.isdigit():
            # do nothig
            # lines_sentences.append(line)
            return
        elif '-->' in line:
            if state == s_init or state == s_de_end:
                ts1 = line
                state = s_ts
                return
            elif state == s_de_start:
                if any(char in next_line for char in ('.', '!', '?')):
                    ts2 = line
                    return
                else:
                    if ts1 == "":
                        raise ValueError("cannot happen ts1 empty")
                    # skip ts
                    return
            else:
                raise ValueError("cannot happen 1")
        else:
            # subtitle text
            if state == s_init:
                raise ValueError("cannot happen 2")

            if state == s_ts:
                if line.endswith(('.', '!', '?')):
                    state = s_de_end
                    lines_sentences.append(build_ts(ts1, ts1))
                    lines_sentences.append(line)
                    sentence = ""
                    return
                else:
                    state = s_de_start
                    # ts1 = line
                    # ts2 = ""
                    sentence = line
                    return
            elif state == s_de_start:
                if any(char in line for char in ('.', '!', '?')) and not line.endswith(('.', '!', '?')):
                    lines_sentences.append(build_ts(ts1, ts2))
                    lines_sentences.append(sentence + " " + line)
                    if ts2 == "":
                        raise ValueError("cannot happen ts2 empty")
                    ts1 = ts2
                    ts2 = ""
                    sentence = line
                    return
                elif line.endswith(('.', '!', '?')):
                    lines_sentences.append(build_ts(ts1, ts2))
                    lines_sentences.append(sentence + line)
                    ts1 = ""
                    ts2 = ""
                    sentence = ""
                    state = s_de_end
                    return
                else:
                    sentence += " " + line
                    return
            else:
                raise ValueError("cannot happen 3")

    print("lines_preprocessed:", len(lines_preprocessed))
    for l in lines_preprocessed:
        print(l.strip())

    lines_sentences = []
    if do_break_into_sentences:
        i = 0
        while i < len(lines_preprocessed):
            line = lines_preprocessed[i].strip()
            if i + 1 < len(lines_preprocessed):
                next_line = lines_preprocessed[i + 1].strip()
            else:
                next_line = ""
            sm_process(line, next_line, lines_sentences)
            i += 1

        if sentence != "":
            raise ValueError(f"sentence non empty: {sentence}")
    else:
        i = 0
        while i < len(lines_preprocessed):
            line = lines_preprocessed[i].strip()
            if '-->' in line:
                line = build_ts(line, line)
            lines_sentences.append(line)
            i += 1

    print("lines_sentences:", len(lines_sentences))
    for l in lines_sentences:
        print(l.strip())

    german_lines_to_translate = []
    i = 0
    while i < len(lines_sentences):
        ts = lines_sentences[i]
        text = lines_sentences[i + 1]
        german_lines_to_translate.append(text)
        i += 2

    print("german_lines_to_translate:", len(german_lines_to_translate))

    from src.lib_clean.lib_google_do_translate import translate_batch
    from src.lib_clean.lib_gcp_do_translate import translate_de
    # Now perform batch translation of all collected German lines
    if not gcp_translate:
        batch = []
        sub_batches_num = []
        for t in german_lines_to_translate:
            parts = break_de_text_to_sentences(t)
            parts = filter_strings_with_alnum(parts)
            batch.extend(parts)
            sub_batches_num.append(len(parts))


        english_translations_batch = translate_batch(batch, "en")

        # --- CORRECTED Reconstruction Logic ---
        english_translations = []
        current_index = 0  # Keep track of our position in english_translations_batch
        for num_parts in sub_batches_num:  # Iterate based on the number of parts per original line
            # Slice the translated batch to get the parts for the current original line
            parts_for_this_line = english_translations_batch[current_index: current_index + num_parts]

            # Join these parts back into a single string
            english_translations.append(" ".join(parts_for_this_line))

            # Update the index to the start of the parts for the next original line
            current_index += num_parts
        # --- End of CORRECTED Logic ---

        # Now english_translations should contain the correctly reconstructed translated lines

    def create_file(output_file_name, lr_format):
        with open(output_file_name, 'w', encoding='utf-8') as f:
            i = 0
            while i < len(lines_sentences):
                ts = lines_sentences[i]
                if lr_format:
                    ts += " " + orig_file_name_cleaned
                text = lines_sentences[i + 1]
                if gcp_translate:
                    # english_translations_local = batch_translate_german_to_english([text])
                    translation = translate_de(text)
                    # translation = english_translations_local[0]
                    # english_translations_local = batch_translate_german_to_english([text])
                    # translation = english_translations_local[0]
                else:
                    translation = english_translations[int(i/2)]

                if not lr_format:
                    f.write(f"{int(1 + i/2)}" + "\n")
                f.write(ts + "\n")
                f.write(text + "\n")
                f.write(translation + "\n")
                f.write("\n")
                # f.writelines(["" + i, ts, text, english_translations[0], ""])

                i += 2

    from src.lib_clean.lib_do_translate_cache import save_translation_cache

    create_file(output_file_srt_translated, False)
    print("output_file_srt_translated: " + output_file_srt_translated)
    create_file(output_file, True)
    print("output_file: " + output_file)

    save_translation_cache()

    if False:
        # Now perform batch translation of all collected German lines
        english_translations = batch_translate_german_to_english(german_lines_to_translate)

        # We now need to replace placeholders in the file with actual translations.
        # Since we have already written the file, let's do a second pass:
        with open(output_file, 'r', encoding='utf-8') as f:
            output_lines = f.readlines()

        # Replace TRANSLATION_PLACEHOLDER lines with actual translations
        translation_index = 0
        for idx, line in enumerate(output_lines):
            if "TRANSLATION_PLACEHOLDER" in line:
                output_lines[idx] = english_translations[translation_index] + "\n\n"
                translation_index += 1

        # Write final output
        with open(output_file, 'w', encoding='utf-8') as f:
            f.writelines(output_lines)

        print(f'Translation complete. Output saved to {output_file}')
        save_translation_cache()
