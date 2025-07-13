# LangRepeater German learning python STT/TTS/ML tool stack
The main idea behind this learning approach is listening to custom/individually made media material where each german word/phrase is auto translated and repeated 3 times. This allows to consume german material and improve vocabulary combining german learning with your everyday activities(dish washing, walking, gym, etc.). There is no need to rewind back to hear the phrase again of pause to translated word.
There are 2 types of materials supported by The LangRepeater German learning stack: 
1. Text(markdown) material. The LangRepeater German learning stack support any material in form of markdown output from any LLM(ChatGpt, Gemini, etc.).
The LLM output will be parsed, german words and phrases will be detected using ML model https://huggingface.co/igorsterner/german-english-code-switching-identification
And then DE or EN google cloud platform TTS(text to speech) will generate speech for each segment separately to improve TTS quality.
Then video/audio track with subtitles is specially compiled so each german phrase is repeated 3 times followed by auto translated to english speech.
Generated Video media can be played in any video player on phone or laptop. Also for better experience I developed android app(https://github.com/konstantin-eu/lr-player) that uses generated audio track with subtitles. The app supports rewind by subtitles(jump to text/prev subttile) and text copying which improves experience greatly. For details see [langrepeater_md.py](src/langrepeater_md.py) section below.
example video https://www.youtube.com/watch?v=M8L4Ac__jgU generated from German Possessive Adjectives markdown [example1.md](examples_md/example1.md) produced by chetGpt using prompt "Provide example phrases in German to remember German possessive adjectives for 1st person singular".  
TODO write to igorsterner/german-english-code-switching-identification to add reference
TODO write openai discussion regarding hallucination reduction

2. Audio(wav file) material. Could be movie, song, any material. The audion file is transcribed special way to reduce model hallucinations using TTS model Faster Whisper. Transcription is broken down into complete sentences. Each complete german sentecnce is combined with aoto translated to english text and final subtitle is generated. Then special video player for windows(TODO add link) can be used with support of repetition of each subtitle and rewinding to the next subtitle - very convenient for Language learning. TODO. add video player link. Or my android app(TODO add link) can be used same way, except only audio track(no video) is played.
TODO add example video and android app

# requirements
GCP account for TTS. For eng TTS base voice is used, practically cost free, there is some free amount per months that is hard use.
for German tts poly voice ? is used, from my experience practically cost free.

install ffmpeg, make command available in PATH command line

# installation/build/config

pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

pip install -r requirements.txt

create src/langrepeater_app/.env from src/langrepeater_app/.env.template

make GCP setup for STT (link???)

I'm building and testing in windows 11, python 3.12, GPU NVIDIA GeForce RTX 4060 Ti


# commands with arguments
[langrepeater_md.py](src/langrepeater_md.py)
```
usage: langrepeater_md.py [-h] [-o OUTFILE] [--create_audio] infile
```
infile - markdown file, can be LLM(cheatGpt) output with german learning material(grammar, phrases, word examples)
OUTFILE - override where to store langrepeater txt format file
--create_audio - create audio and subtitles instead of video file for android app (TODO link to android app)


[langrepeater_whisper.py](src/langrepeater_whisper.py)
~~~
usage: langrepeater_whisper.py [-h] [--lrtxt_outdir LRTXT_OUTDIR]
                               [--create_audio]
                               infile
~~~
The commands produces special subtitles using faster whisper. TPlease not this is not just a transcription using Whisper, instead following os done:
a) by default Openai Whisper and Faster Whisper (https://github.com/SYSTRAN/faster-whisper) transcription quality can be not good because of hallucinations(for details see https://github.com/openai/whisper/discussions/1783 , from my understanding, especially for non english speech). To mitigate this problem I first detect speech segments in audio track using https://github.com/snakers4/silero-vad and then run faster whisper STT model with speech segments
b) transcription with word timestamps are generated
c) transcription is broken down into complete sentences https://spacy.io/ and subtitles are generated
d) english translation is added to german subtitles
e) Optionally my special windows Video player can be used with support of repetition of each subtitle and rewinding to the next subtitle - very convenient for Language learning. TODO. add video player link.

infile - wav file with german speech (could be anything, movies, podcasts, songs, learning materials)
--create_audio - create audio and subtitles instead of video file for android app (TODO link to android app)
example infile in git:
audio/fairytale_1.wav

When video is generated(--create_audio is not set) - my special windows Video player can by used with support of repetition of each subtitle and rewinding to the next subtitle - very convenient for Language learnig. 


# app dir
includes tts cache and out dir with generated media
c:\Users\<username>\AppData\Local\langrepeater\


# Note on Code Generation
Parts of this project were programmed with the assistance of a large language model (LLM).
As such, some code may not reflect standard best practices or optimal design choices.
Contributions and improvements are welcome!

# translation models
TODO

# Contact
Feel free to reach out!
Email: [langrepeater@gmail.com](mailto:langrepeater@gmail.com)
