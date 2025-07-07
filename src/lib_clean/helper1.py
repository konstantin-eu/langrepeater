
import re

def remove_all_non_starting_asterisks_regex(line):
  """
  Removes all asterisks from a line that are not the starting symbol.
  """
  if not line:
    return ""
  # Keep the first character if it's an asterisk
  first_char = line[0]
  rest_of_line = line[1:]

  # Remove all asterisks from the rest of the line
  rest_of_line_cleaned = re.sub(r'\*', '', rest_of_line)

  return first_char + rest_of_line_cleaned

def capitalize_first_letter_in_text(text):
    """
    Capitalizes the first letter found in the text.
    Handles empty strings and strings with no letters.
    Works for Unicode characters (e.g., German umlauts).

    Args:
        text (str): The input string.

    Returns:
        str: The string with its first letter capitalized, or the original
             string if no letters are found or if the string is empty.
    """
    if not text:
        return ""  # Return empty string if input is empty

    for i, char in enumerate(text):
        if char.isalpha():  # Check if the character is a letter
            # Reconstruct the string:
            # part before the letter + capitalized letter + part after the letter
            return text[:i] + char.upper() + text[i+1:]

    # If no letter was found in the string (e.g., "123 !@#"), return it as is.
    return text


if __name__ == "__main__":
    # Examples:
    english_text1 = "hello world"
    english_text2 = "  leading spaces and then text"
    english_text3 = "123numbers before text"
    english_text4 = "!punctuation before text"
    english_text5 = "Already capitalized"
    english_text6 = ""
    english_text7 = "---" # No letters

    german_text1 = "hallo welt"
    german_text2 = "äpfel sind lecker" # Starts with an umlaut
    german_text3 = "  straße mit ß"
    german_text4 = "übung macht den meister"

    print(f"'{english_text1}' -> '{capitalize_first_letter_in_text(english_text1)}'")
    # Output: 'hello world' -> 'Hello world'

    print(f"'{english_text2}' -> '{capitalize_first_letter_in_text(english_text2)}'")
    # Output: '  leading spaces and then text' -> '  Leading spaces and then text'

    print(f"'{english_text3}' -> '{capitalize_first_letter_in_text(english_text3)}'")
    # Output: '123numbers before text' -> '123Numbers before text'

    print(f"'{english_text4}' -> '{capitalize_first_letter_in_text(english_text4)}'")
    # Output: '!punctuation before text' -> '!Punctuation before text'

    print(f"'{english_text5}' -> '{capitalize_first_letter_in_text(english_text5)}'")
    # Output: 'Already capitalized' -> 'Already capitalized'

    print(f"'{english_text6}' -> '{capitalize_first_letter_in_text(english_text6)}'")
    # Output: '' -> ''

    print(f"'{english_text7}' -> '{capitalize_first_letter_in_text(english_text7)}'")
    # Output: '---' -> '---'

    print(f"'{german_text1}' -> '{capitalize_first_letter_in_text(german_text1)}'")
    # Output: 'hallo welt' -> 'Hallo welt'

    print(f"'{german_text2}' -> '{capitalize_first_letter_in_text(german_text2)}'")
    # Output: 'äpfel sind lecker' -> 'Äpfel sind lecker'

    print(f"'{german_text3}' -> '{capitalize_first_letter_in_text(german_text3)}'")
    # Output: '  straße mit ß' -> '  Straße mit ß'

    print(f"'{german_text4}' -> '{capitalize_first_letter_in_text(german_text4)}'")
    # Output: 'übung macht den meister' -> 'Übung macht den meister'