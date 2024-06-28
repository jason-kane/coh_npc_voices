"""
These are high level manipulations of audio files.
"""
from pedalboard.io import AudioFile
from voicebox.tts.utils import get_audio_from_wav_file
import logging

log = logging.getLogger(__name__)


def mp3file_to_wavfile(mp3filename, wavfilename=None):
    """
    Pedelboard can convert mp3 to wav pretty quickly/easily.
    
    This is more or less straight from the README.md for pedalboard.
    Spotify - Props for pedalboard open source.
    """
    log.info('Converting from mp3 to wav...')
    if wavfilename is None:
        wavfilename = mp3filename + ".wav"

    with AudioFile(mp3filename) as input:
        with AudioFile(
            filename=wavfilename, 
            samplerate=input.samplerate,
            num_channels=input.num_channels
        ) as output:
            while input.tell() < input.frames:
                output.write(input.read(1024))
            log.info(f'Wrote {wavfilename}')
    
    return wavfilename


def mp3file_to_Audio(mp3filename):
    """
    We want this mp3 as a voicebox Voice() object.
    """
    wavfilename = mp3file_to_wavfile(mp3filename)
    return get_audio_from_wav_file(
        wavfilename
    )       
