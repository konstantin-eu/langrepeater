# requirements
GCP account for TTS. For eng TTS base voice is used, practically cost free, there is some free amount per months that is hard use.
for German tts poly voice ? is used, from my experience practically cost free.

install ffmpeg, make command available in PATH command line

# installation/build

pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

pip install -r requirements.txt

create src/langrepeater_app/.env from src/langrepeater_app/.env.template

make GCP setup for STT (link???) 

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
The commands produces special subtitles using faster whisper. TPlease not this is not just a translcribtion using whisper, isnetead floowing os done:
a) by default openai whisper and faster whisper (https://github.com/SYSTRAN/faster-whisper) transcribtion quality can be not good because of hallucinations(https://github.com/openai/whisper/discussions/1783) (from my understanding, especially for non english speech). To mitigate this I first detect speech segments in audio track using https://github.com/snakers4/silero-vad and then run faster whisper STT model with speech segments
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

# license