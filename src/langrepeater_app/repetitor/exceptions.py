# german_repetitor/repetitor/exceptions.py

"""
Custom exception classes for the German Repetitor application.
"""

class RepetitorError(Exception):
    """Base class for all custom exceptions in this application."""
    def __init__(self, message="An error occurred in the Repetitor application", *args):
        super().__init__(message, *args)

class ConfigError(RepetitorError):
    """Exception raised for errors in configuration loading or validation."""
    def __init__(self, message="Configuration error", *args):
        super().__init__(message, *args)

class InputError(RepetitorError):
    """Exception raised for errors related to input files or data."""
    def __init__(self, message="Input data error", *args):
        super().__init__(message, *args)

class PhraseParsingError(InputError):
    """Exception raised specifically during the parsing of phrase files."""
    def __init__(self, message="Error parsing phrases", line_number=None, *args):
        self.line_number = line_number
        if line_number is not None:
            message = f"{message} near line {line_number}"
        super().__init__(message, *args)

class ValidationError(RepetitorError):
    """Exception raised for text format validation errors."""
    def __init__(self, message="Text validation failed", *args):
        super().__init__(message, *args)

class AudioProcessingError(RepetitorError):
    """Exception raised for errors during audio generation or processing."""
    def __init__(self, message="Audio processing error", *args):
        super().__init__(message, *args)

class VideoProcessingError(RepetitorError):
    """Exception raised for errors during video generation (e.g., FFmpeg errors)."""
    def __init__(self, message="Video processing error", command=None, stderr=None, *args):
        self.command = command
        self.stderr = stderr
        if command:
            message = f"{message} while running command: {' '.join(command)}"
        if stderr:
            message = f"{message}\nFFmpeg stderr:\n{stderr}"
        super().__init__(message, *args)

class GoogleCloudError(RepetitorError):
    """Exception raised for errors interacting with Google Cloud APIs."""
    def __init__(self, message="Google Cloud API error", service=None, *args):
        self.service = service
        if service:
            message = f"{message} in service: {service}"
        super().__init__(message, *args)

# Example of how to raise an exception:
# if config_value is None:
#     raise ConfigError("Required configuration value 'XYZ' is missing.")

# Example of catching a specific exception:
# try:
#     process_audio(data)
# except AudioProcessingError as e:
#     logger.error(f"Failed to process audio: {e}")
#     # Handle specific audio error
# except RepetitorError as e:
#     logger.error(f"A general Repetitor error occurred: {e}")
#     # Handle other application errors
