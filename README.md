# LangRepeater: German Learning Tool with Python, STT/TTS, and ML

The main idea behind this learning approach is to listen to custom, individually created media materials where each German word or phrase is automatically translated and repeated three times. This allows you to consume German content and improve your vocabulary while combining language learning with everyday activities (e.g., dishwashing, walking, or going to the gym). There's no need to rewind to hear a phrase again or pause to look up translations.

LangRepeater supports two types of materials:
1. **Text (Markdown) Material**: The stack supports any material in Markdown format, such as output from LLMs (e.g., ChatGPT, Gemini). The Markdown is parsed, and German words/phrases are detected using the ML model from [igorsterner/german-english-code-switching-identification](https://huggingface.co/igorsterner/german-english-code-switching-identification). Google Cloud Platform TTS (Text-to-Speech) generates speech for each segment separately (using DE or EN voices) to improve quality. A video/audio track with subtitles is then compiled, where each German phrase is repeated three times, followed by its English translation. The generated video can be played in any video player on a phone or laptop. For a better experience, use the custom Android app ([konstantin-eu/lr-player](https://github.com/konstantin-eu/lr-player)), which supports the audio track with subtitles, rewinding by subtitle, jumping to previous subtitles, and text copying. For details, see the [langrepeater_md.py](#langrepeater_mdpy) section below.

   Example video: [YouTube](https://www.youtube.com/watch?v=M8L4Ac__jgU), generated from the German Possessive Adjectives Markdown file [example1.md](examples_md/example1.md), produced by ChatGPT using the prompt: "Provide example phrases in German to remember German possessive adjectives for 1st person singular."

2. **Audio (WAV File) Material**: This can be from movies, songs, or any other source. The audio is transcribed using Faster Whisper to reduce model hallucinations. The transcription is broken down into complete sentences, each combined with an auto-translated English version to generate subtitles. Use the custom Windows video player ([konstantin-eu/lr-player-wpf](https://github.com/konstantin-eu/lr-player-wpf)) for repetition of each subtitle and rewinding to the next one—ideal for language learning. Alternatively, the Android app ([konstantin-eu/lr-player](https://github.com/konstantin-eu/lr-player)) can play the audio track (without video) with the same features.

   Example video: [YouTube](https://www.youtube.com/watch?v=XFTBIWYSbRA), from [german_fairytale_llm_1.wav](audio/german_fairytale_llm_1.wav).

## Requirements
- A Google Cloud Platform (GCP) account for TTS. The English TTS uses a base voice (practically cost-free with monthly free quotas). The German TTS uses the Polyglot voice ([cloud.google.com/text-to-speech/docs/polyglot](https://cloud.google.com/text-to-speech/docs/polyglot)), which is also effectively cost-free based on typical usage.
- Install FFmpeg and ensure the `ffmpeg` command is available in your PATH.

## Installation, Build, and Configuration
- Install PyTorch with CUDA support (for GPU acceleration):
  ```
  pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
  ```
- Install project dependencies:
  ```
  pip install -r requirements.txt
  ```
- Create `src/langrepeater_app/.env` from `src/langrepeater_app/.env.template`.
- Set up GCP for Python TTS: Follow the guide at [cloud.google.com/python/docs/setup](https://cloud.google.com/python/docs/setup).

This project was built and tested on Windows 11 with Python 3.12 and an NVIDIA GeForce RTX 4060 Ti GPU.

## Usage: Commands and Arguments

### langrepeater_md.py
Processes Markdown files for German learning material (e.g., grammar, phrases, word examples from LLMs like ChatGPT).

```
usage: langrepeater_md.py [-h] [-o OUTFILE] [--create_audio] infile
```
- `infile`: Path to the Markdown file.
- `-o OUTFILE` / `--outfile OUTFILE`: Override the output path for the LangRepeater TXT format file.
- `--create_audio`: Generate audio and subtitles (instead of a video file) for the Android app ([konstantin-eu/lr-player](https://github.com/konstantin-eu/lr-player)).

### langrepeater_whisper.py
Generates special subtitles using Faster Whisper STT (Speech-to-Text). Note: This is not a simple transcription. Instead:
- Speech segments are detected using [snakers4/silero-vad](https://github.com/snakers4/silero-vad) to mitigate hallucinations in OpenAI Whisper/Faster Whisper (see discussion: [openai/whisper#1783](https://github.com/openai/whisper/discussions/1783)).
- Transcriptions with word timestamps are generated.
- Text is broken into complete sentences using [spaCy](https://spacy.io/).
- English translations are added to German subtitles.

If `--create_audio` is not set, a video is generated that can be played in the custom Windows video player ([konstantin-eu/lr-player-wpf](https://github.com/konstantin-eu/lr-player-wpf)) with subtitle repetition and rewinding features.

```
usage: langrepeater_whisper.py [-h] [--lrtxt_outdir LRTXT_OUTDIR] [--create_audio] infile
```
- `infile`: Path to the WAV file with German speech (e.g., movies, podcasts, songs, learning materials). Example in repo: [fairytale_1.wav](audio/fairytale_1.wav).
- `--lrtxt_outdir LRTXT_OUTDIR`: Override the output directory for LangRepeater TXT files.
- `--create_audio`: Generate audio and subtitles (instead of a video file) for the Android app ([konstantin-eu/lr-player](https://github.com/konstantin-eu/lr-player)).

## App Directory
Includes TTS cache and output directory for generated media:  
`C:\Users\<username>\AppData\Local\langrepeater\`

## Note on Code Generation
Parts of this project were programmed with the assistance of a large language model (LLM). As such, some code may not reflect standard best practices or optimal design choices. Contributions and improvements are welcome!

## Translation Models
- [facebook/nllb-200-distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [jbochi/madlad400-3b-mt](https://huggingface.co/jbochi/madlad400-3b-mt)

## Contact
Feel free to reach out!  
Email: [langrepeater@gmail.com](mailto:langrepeater@gmail.com)