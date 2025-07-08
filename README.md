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
[langrepeater_whisper.py](src/langrepeater_whisper.py)

need example wav for
[langrepeater_whisper.py](src/langrepeater_whisper.py)
add examples folder with wav file / or link

# cache and out dir
c:\Users\<username>\AppData\Local\langrepeater\
