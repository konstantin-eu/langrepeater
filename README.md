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
OUTFILE - override where to store langrepeater txt format file
--create_audio - create audio and subtitles instead of video file for android app (TODO link to android app)


[langrepeater_whisper.py](src/langrepeater_whisper.py)

[langrepeater_whisper.py](src/langrepeater_whisper.py)
example:
audio/fairytale_1.wav


# app dir
includes tts cache and out dir with generated media
c:\Users\<username>\AppData\Local\langrepeater\


# Note on Code Generation
Parts of this project were programmed with the assistance of a large language model (LLM).
As such, some code may not reflect standard best practices or optimal design choices.
Contributions and improvements are welcome! 

# license