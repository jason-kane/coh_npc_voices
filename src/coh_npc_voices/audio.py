from pedalboard.io import AudioFile
from voicebox.tts.utils import get_audio_from_wav_file
import logging

log = logging.getLogger('__name__')


def mp3file_to_wavfile(mp3filename, wavfilename=None):
    # Pedelboard can convert mp3 to wav pretty quickly/easily.
    # but I really ought to pull this out to a function
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
    wavfilename = mp3file_to_wavfile(mp3filename)
    return get_audio_from_wav_file(
        wavfilename
    )       
