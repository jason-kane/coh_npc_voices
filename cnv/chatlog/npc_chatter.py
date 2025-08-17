import glob
import hashlib
import io
import colorsys
import logging
import webcolors
import os
import re
import random
import queue
import threading
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

import cnv.lib.settings as settings
import pygame
import pythoncom
from pedalboard.io import AudioFile

import cnv.database.models as models
import cnv.logger
import cnv.voices.voice_builder as voice_builder
from cnv.lib.proc import send_log_lock

from cnv.chatlog import patterns

from cnv import engines


cnv.logger.init()
log = logging.getLogger(__name__)

console = Console()

# so frequently enough to merit this; people will identify themselves in the CAPTION messages.
# like:
# 2024-04-26 18:40:13 [Caption] <scale 1.75><color white><bgcolor DarkGreen>Positron here. I'm monitoring your current progress in the sewers.
# we want to use that voice for captions until we find out otherwise.  This way they can have their own voice.
#                     INFO     cnv.chatlog.npc_chatter: CAPTION: ['[Caption]', '<scale', '175><color', 'white><bgcolor', 'DarkGreen>Positron', 'here', "I'm",            npc_chatter.py:381                             'monitoring', 'your', 'current', 'progress', 'in', 'the', 'sewers']
CAPTION_SPEAKER_INDICATORS = (
    ('Positron here', 'Positron'),
    ('Matthew, is it', 'Dana'),  # Cinderburn mission
    ("Dana you're alive?!", 'Matthew'),
    ("This is Penelope Yin!", 'Penelope Yin'),
    ('This is Robert Alderman', 'Robert Alderman'),
    ('this is Watkins.', 'Agent Watkins'),
)


class TightTTS(threading.Thread):
    def __init__(self, speaking_queue, event_queue):
        threading.Thread.__init__(self)
        self.speaking_queue = speaking_queue
        self.event_queue = event_queue
        self.daemon = True
        self.all_npcs = {}

        # so we can do this much once.
 
        
        for category in ["npc", "player", "system"]:
            for dir in [
                settings.clip_library_dir(),         
                os.path.join(settings.clip_library_dir(), category),
            ]:
                try:
                    os.mkdir(dir)
                except OSError:
                    # the directory already exists.  This is not a problem.
                    pass
        self.start()


    def get_channel(self, name: str, category: str) -> pygame.mixer.Channel:
        if category == "system":
            channel_index = 0
        else:
            # okay.. with apologies for the level of fancy here. we
            # don't want characters to be able to talk over
            # themselves, because that is stupid.
            
            # But.. we are also limited to a small number of
            # channels relative to the number of characters.  We
            # can't give _every_ character a unique channel.  Lets
            # try spreading them out randomly across the channels
            # that we have.

            # lets hash our npc names into channels, for the armchair
            # enthusiasts out there:
            
            # we have (lets say) 8 audio channels. 
            # we have (again), lets say 80 characters.  
        
            # We never want a character to talk over themselves, it's
            # just too blatently stupid.  Having some, even most
            # characters able to talk over each other is fine.  Having a
            # few characters that never talk over each other is a little
            # weird, but not all that weird.  Acceptable weird.

            # This takes the characters unique name string, and converts
            # it into a reasonably small number (4 hex characters long,
            # 0-65535 ) this particular name will always give this
            # particular number there are many other names that just
            # might also give this number.  It doesn't matter as long as
            # it's reasonably unlikely.
            
            # Because the next thing we do is use a modulus to map any
            # of the possible 0-65535 possible values for the name
            # evenly across a list of buckets, one per audio channel.

            # we could cache the name->integer call easily, that trades a cache lookup for a sha encoding.

            # we're reserving channel 0 for the system, hence the -1 here.

            # the modulus left us with buckets (0..max channel - 1), but we want 
            # channels (1..max_channel), hence 1 + 
            if name:
                channel_index = 1 + int(hashlib.sha256(name.encode()).hexdigest()[:3], 16) % (len(self.channels) - 1)
            else:
                log.error('Invalid channel: name: %s  category: %s', name, category)
                return random.choice(self.channels)

        return self.channels[channel_index]


    def play(self, channel, wav_fn):
        # is there an audio already queued?
        if channel.get_queue():
            # we have to wait until a spot is available or we're going to drop audio.
            
            # I really don't like polling interfaces like this.  pygame has ways to 
            # do this in an async or callback style.
            while channel.get_queue():
                log.debug(f'[TightTTS.play()] Waiting for channel {channel} queue availability...')
                pygame.time.wait(250)  # milliseconds
        
        # play this file on this channel, but if you're already
        # playing something let it finish.  No need to be rude.
        log.debug('[TightTTS.play()] invoking %s.queue(Sound(%s))', channel, wav_fn)
        channel.queue(
            pygame.mixer.Sound(file=wav_fn)
        )
        log.debug('[TightTTS.play()] Play Complete')


    def run(self):
        log.info('[TightTTS] !! TightTTS is RUNNING !!')
        
        pygame.mixer.init()
        pygame.mixer.set_num_channels(8)

        self.channels = [
            pygame.mixer.Channel(0),
            pygame.mixer.Channel(1),
            pygame.mixer.Channel(2),
            pygame.mixer.Channel(3),
            pygame.mixer.Channel(4),
            pygame.mixer.Channel(5),
            pygame.mixer.Channel(6),
            pygame.mixer.Channel(7),
        ]

        pythoncom.CoInitialize()
        raw_message = None
        
        while True:
            log.debug('[TightTTS] Top of True')
            while self.speaking_queue.empty():
                time.sleep(0.25)

            played = False
            log.debug('Retrieving queued message')
            raw_message = self.speaking_queue.get()

            log.debug('[TightTTS] TTS Message received: %s', raw_message)
            # we got a message
            try:
                name, message, category = raw_message
            except ValueError:
                log.warning("[TightTTS] Unexpected queue message: %s", raw_message)
                continue
            raw_message = None

            if category not in ["npc", "player", "system"]:
                log.error("[TightTTS] invalid category: %s", category)
                self.speaking_queue.task_done()
                continue

            phrase_id = models.get_or_create_phrase_id(name, category, message)
            message, is_translated = models.get_translated(phrase_id)
            
            log.debug('Retrieving get_channel(name=%s, category=%s)', name, category)
            channel = self.get_channel(name=name, category=category)

            log.debug(f"[TightTTS] Speaking thread received {category} {name}:{message}")

            for rank in ['primary', 'secondary']:
                cachefile = settings.get_cachefile(name, message, category, rank)
                wav_fn = str(cachefile + ".wav")
                # if primary exists, play that.  else secondary.

                # we really want wav_fn to exist, if we can.  Makes this all easier when it exists.
                if os.path.exists(wav_fn):
                    # log.info(f'[TightTTS] [{category}][{channel}] Playing wav file {wav_fn}')
                    self.play(channel=channel, wav_fn=wav_fn)
                    played = True
                    break
                else:
                    # uh oh, maybe the mp3 version of this file exists?
                    if os.path.exists(cachefile + ".mp3"):
                        log.debug(f"[TightTTS] (tighttts) Cache HIT: {cachefile}")
                        # requires pydub?
                        # what the hell are we doing? it sure as fuck looks like we're
                        # copying "cachefile" to "cachefile.wav".. fuck that noise, it's a damn mp3.
                        # we're converting an mp3 into a wav file.  that is what this noise is.
                        with AudioFile(cachefile + ".mp3", mode="r") as input:
                            with AudioFile(
                                wav_fn,
                                mode="w",
                                samplerate=input.samplerate,
                                num_channels=input.num_channels,
                            ) as output:
                                while input.tell() < input.frames:
                                    output.write(input.read(1024))                       
                        
                        log.debug(f'[TightTTS] [{category}][{channel}] Playing wav file {wav_fn}')
                        self.play(channel=channel, wav_fn=wav_fn)
                        played = True
                        break

            # building session out here instead of inside get_character
            # keeps character alive and properly tied to the database as we
            # pass it into update_character_last_spoke and voice_builder.
            if not played:
                with models.db() as session:
                    character = models.Character.get(name, category, session)

                    models.update_character_last_spoke(character.id, session)

                    # it isn't very well named, but this will speak "message" as
                    # character and cache a copy into cachefile.
                    try:
                        voice_builder.create(character, message, session)
                    
                        for rank in ['primary', 'secondary']:
                            try:
                                cachefile = settings.get_cachefile(name, message, category, rank)
                                wav_fn = str(cachefile + ".wav")
                            
                            except (engines.elevenlabs.InvalidVoiceException):
                                log.error(f"Invalid voice for ElevenLabs: {name}")
                                continue

                            except Exception as err:
                                log.error(f"Error occurred generating audio: {err}")
                                raise

                            if os.path.exists(wav_fn):
                                self.play(channel=channel, wav_fn=wav_fn)
                                played = True
                                break

                    except Exception as err:
                        raise


def plainstring(dialog):
    """
    Clean up any color codes and give us just the basic text string
    """
    dialog = re.sub(r"<scale [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<bordercolor [#a-zA-Z0-9]+>", "", dialog).strip()
    return dialog


def luminance(rgb_hexstring):
    """
    Returns a value between 0 (black) and 255 (pure white)
    """
    red, green, blue = webcolors.hex_to_rgb(rgb_hexstring)
    return (.299 * red) + (.587 * green) + (.114 * blue)


def adjust_brightness(rgb_hexstring, change=0.1):
    """
    Convert to HSL, increase luminance, convert back to RGB.
    """
    log.debug('Adjusting brightness of %s by %s', rgb_hexstring, change)
    # we want 0-1 floats for each color
    red, green, blue = [x / 255.0 for x in webcolors.hex_to_rgb(rgb_hexstring)]
    hue, luminosity, saturation = colorsys.rgb_to_hls(red, green, blue)
    
    log.debug('Luminosity before: %s', luminosity)
    
    luminosity += change
    luminosity = min(1.0, luminosity)
    luminosity = max(0.0, luminosity)
    
    log.debug('Luminosity after: %s', luminosity)

    # and back to 0-255 values 
    red, green, blue = [int(x * 255) for x in colorsys.hls_to_rgb(hue, luminosity, saturation)]
    log.debug('As 0-255 tuple: (%s, %s, %s)', red, green, blue)

    # and back to a hex string
    hexstr = webcolors.rgb_to_hex((red, green, blue))
    log.debug('Adjustment complete.  New color: %s', hexstr)
    return hexstr


def darken(rgb_hexstring, value=0.1):
    """
    Return the same color but a little darker
    """
    return adjust_brightness(rgb_hexstring, change=-1 * value)


def lighten(rgb_hexstring, value=0.1):
    """
    Return the same color but a little brighter
    """
    return adjust_brightness(rgb_hexstring, change=value)


def color_contrast(fg_luminance, bg_luminance):
    fg_luminance /= 255
    bg_luminance /= 255

    contrast = (
        max((fg_luminance, bg_luminance)) + 0.05
    ) / (
        min((fg_luminance, bg_luminance)) + 0.05
    )    
    return contrast


def expand_contrast(fgcolor, bgcolor, threshold=10):
    fg_luminance = luminance(fgcolor)
    bg_luminance = luminance(bgcolor)
    
    contrast = color_contrast(fg_luminance, bg_luminance)

    while contrast < threshold:   
        # light on dark or dark on light?
        if fg_luminance > bg_luminance:
            # light on dark, pull them further apart
            bgcolor = darken(bgcolor)
            fgcolor = lighten(fgcolor)
        else:
            # dark on light, pull them further apart
            bgcolor = lighten(bgcolor)
            fgcolor = darken(fgcolor)

        fg_luminance = luminance(fgcolor)
        bg_luminance = luminance(bgcolor)

        contrast = color_contrast(fg_luminance, bg_luminance)

    return fgcolor, bgcolor, contrast


def colorstring(dialog):
    """
    dialog might be something like:

    Mr. Delaine: <color #38a7ff><bgcolor #010101>wanted to make sure they stacked before getting it
    Albiorix Albici: <color #010101>It's not, but who knows.
    Lightslinger: <color #0101fb><bgcolor #ffff01>modified enough and it's not a worry
    """
    if dialog is None:
        return ""

    # Impulse: <color #40ff01><bgcolor #010101>speed tinpex lfm, pst 2/8
    for tag, color in [
        ['color', '#FFFFFF'], ['bgcolor', '#000000']
    ]:

        if f"<{tag}" in dialog:
            color_match = re.match(
                r"(?P<before>.*)<" + tag + r" (?P<color>#?[a-zA-F0-9]*)>(?P<after>.*)",
                dialog,
                re.IGNORECASE
            )

            if color_match is not None:
                color = color_match.group('color')
                if "#" not in color:
                    color_rgb = webcolors.name_to_rgb(color)
                    color = webcolors.rgb_to_hex(color_rgb)

                before = color_match.group('before')
                after = color_match.group('after')
                dialog = f"{before}{after}"
            else:
                # our regex failed, but it could be a named color
                color_match = re.match(
                    r"(?P<before>.*)<color (?P<color>[a-zA-Z]*)>(?P<after>.*)",
                    dialog,
                    re.IGNORECASE
                )
                if color_match is not None:
                    # potentially a named color
                    try:
                        color_rgb = webcolors.name_to_rgb(color_match.group('color'))
                        color = webcolors.rgb_to_hex(color_rgb)
                                       
                        before = color_match.group('before')
                        after = color_match.group('after')
                        dialog = f"{before}{after}"
                    except ValueError:
                        pass

        if tag == "color":
            fg_color = color
        elif tag == "bgcolor":
            bg_color = color

    # adjust to meet contrast requirements, so black on black turns into grey on black
    fg_color, bg_color, contrast = expand_contrast(fg_color, bg_color)

    # log.debug(f'fgcolor: {fg_color}  bgcolor: {bg_color}  contrast: {contrast}')
    dialog = f"[{fg_color} on {bg_color}]{dialog}[/]"

    return dialog

DARKEST_SOAK = 5  # for how many seconds after the first darkest night do we want to ignore subsequent messages?

class LogStream:
    """
    This is a streaming processor for the log file.  Its kind of sorely
    deficient in more than one way but seems to be at least barely adequate.
    """
    
    # if we don't get any new lines in this many seconds, double check to make
    # sure we're actually reading the most recent log file.  I think a float
    # would work here too.
    READ_TIMEOUT = 60
    previous_stopwatch = {}
    previous_darkest = 0

    # what channels are we paying attention to, which self.parser function is
    # going to be called to properly extract the data from that log entry.
    channel_guide = {
        'NPC': {
            'enabled': True,
            'name': "npc",
            'parser': 'channel_chat_parser'
        },
        'Team': {
            'enabled': True,
            'name': "player",
            'parser': 'channel_chat_parser'
        },
        'Tell': {
            'enabled': True,
            'name': "player",
            'parser': 'tell_chat_parser'
        },
        'Caption': {
            'enabled': True,
            'name': "npc",
            'parser': 'caption_parser'
        }
    }

    def __init__(
        self,
        logdir: str,
        speaking_queue: queue.Queue,
        event_queue: queue.Queue,
        badges: bool,
        npc: bool,
        team: bool,
    ):
        """
        find the most recent logfile in logdir note which file it is, open it,
        do a light scan to find the beginning of the current characters session.
        There is some character data there we need. Then we skip to the end and
        start tailing.
        """
        self.logdir = logdir
        self.announce_badges = badges
        # TODO: these should be exposed on the configuration page
        self.npc_speak = npc
        self.team_speak = team
        self.tell_speak = True
        self.caption_speak = True
        self.announce_levels = True
        self.hero = None
        # who is (as far as we know) currently speaking as CAPTION ?
        self.caption_speaker = None
        self.caption_color_to_speaker = {}

        # carry these along for I/O
        self.speaking_queue = speaking_queue
        self.event_queue = event_queue

        self.logfile = None
        self.first_tail = True
        log.debug(f'(init) Setting {self.logfile=}')

    def open_latest_log(self):
        all_files = glob.glob(os.path.join(self.logdir, "*.txt"))
        filename = max(all_files, key=os.path.getctime)
        
        log.info(f'(oll) Setting {self.logfile=} = {filename}')
        self.logfile = filename
        return os.path.join(self.logdir, filename)

    def find_character_login(self):
        """0
        Skim through and see if can find the beginning of the current characters
        login.
        """
        hero_name = None
        log.info('find_character_login()')
        # we want the most recent entries of specific strings. This might be
        # better done backwards
        # ,
        #    "r",
        #    encoding="utf-8",
        #)
        with open(self.open_latest_log(), 'r', encoding="utf-8") as handle:
            log.info('Searching for welcome message')
            for line in handle:
                try:
                    datestr, timestr, line_string = line.split(None, 2)
                except ValueError:
                    continue

                lstring = line_string.split()
                
                if lstring[0] == "Welcome":
                    # Welcome to City of Heroes, <HERO NAME>
                    self.is_hero = True
                    hero_name = " ".join(lstring[5:]).strip("!")
                    # we want to notify upstream UI about this.
                elif lstring[0:5] == ["Now", "entering", "the", "Rogue", "Isles,"]:
                    # 2024-04-17 17:10:27 Now entering the Rogue Isles, Kim Chee!
                    self.is_hero = False
                    hero_name = " ".join(lstring[5:]).strip("!")
                
                if hero_name:
                    break
                else:
                    log.debug(lstring)

        log.debug("hero_name: %s", hero_name)
        if hero_name:
            self.hero = Hero(hero_name)
            
            if self.event_queue:
                self.event_queue.put(("SET_CHARACTER", self.hero.name))

            if not settings.REPLAY:
                send_log_lock()
                log.info('log_lock attached')

        else:
            self.ssay("User name not detected")
            log.warning("Could NOT find hero name.. good luck.")

    def channel_chat_parser(self, lstring):
        speaker, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
        dialog = plainstring(dialog)
        return speaker, dialog

    def tell_chat_parser(self, lstring):
        """
        Who is talking, what are they saying?
        """
        # why is there an extra colon for Tell?  IDK.        
        if lstring[1][:3] == "-->":
            # note: target names with spaces are not parsed
            # ["[Tell]", "-->Toxic", "Timber:", "pls"]
            # this is a reply to a tell, or an outbound tell.

            # these are self-tells so we have to catch both of them, but we only
            # need to process one of them.  For no particular reason
            # we're going to use the --> inbound message.

            # [Tell] :Ghlorius: [SIDEKICK] name="Ghlorius" 
            # [Tell] -->Ghlorius: [SIDEKICK] name="Ghlorius"
            dialog = (
                " ".join(lstring[1:]).split(":", maxsplit=1)[-1].strip()
            )

            if dialog.split()[0] == "[SIDEKICK]":
                log.info('Parsing SIDEKICK')
                # player attribute self-reporting
                # key=value;key2=value2
                _, all_keyvals = dialog.split(None, maxsplit=1)

                for keyvalue in all_keyvals.split(';'):
                    try:
                        key, value = keyvalue.strip().split('=')
                    except ValueError:
                        log.warning(f'Invalid SIDEKICK: {dialog}')
                        return "__self__", None    

                    settings.set_config_key(
                        key, 
                        value.strip('"'),
                        cf='state.json'
                    )

                # don't try and speak it.
                return "__self__", None

            speaker = "__self__"
        else:
            # ["[Tell]", ":Dressy Bessie:", "I", "can", "bump", "you"]
            # ["[Tell]", ":StoneRipper:", "it:s", "underneath"]
            speaker = None
            dialog = None
            try:
                # ["", "Dressy Bessie", "I can bump you"]
                # ['', 'StoneRipper', ' it:s underneath']
                full_string = " ".join(lstring[1:])

                if ':' in full_string:
                    _, speaker, dialog = full_string.split(
                        ":", maxsplit=2
                    )
                    # ignore SIDEKICK self-tells 
                    try:
                        if dialog.split()[0] == "[SIDEKICK]":
                            return "__self__", None
                    except IndexError:
                        pass

            except ValueError:
                # 2024-07-27 17:17:07 [Tell] You are banned from talking for 2 minutes, 0 seconds.
                # logging at info so I can maybe catch it in the future.
                log.info(f'1 ADD DOC: {lstring=}')
                speaker, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
        
        dialog = plainstring(dialog)
        return speaker, dialog

    def caption_parser(self, lstring):
        """
        Caption messages are a liitle.. fun.  Usually the first message from a
        given speaker identifies the speaker by name but subsequent messages do
        not.  They do consistently use the same background color for each
        speaker.  So we notice when a named speaker introduces themselves then
        we associate that bgcolor with that speaker so we can use the same
        voice.

        A good test for this is the back and forth dialog between Dana and
        Matthew.

        The key data here are the strings in CAPTION_SPEAKER_INDICATORS linking
        introduction messages to speakers.  It will need to be significantly
        expanded to cover more 'caption' speakers.
        """
        # [Caption] <scalxe 2.75><color red><bgcolor White>My Shadow Simulacrum will destroy Task Force White Sands!
        # [Caption] <scale 1.75><color white><bgcolor DarkGreen>Positron here. I'm monitoring your current progress in the sewers. 
        log.debug(f'CAPTION: {lstring}')
        dialog = plainstring(" ".join(lstring[1:]))
        dialog = dialog.replace('*', '')  # the stupid TTS engine say "asterisk" and it is tediously dumb.

        # make an effort to identify the speaker
        # Positron here. I'm monitoring your current progress in the sewers.
        tags = {keyvalue.split()[0]: keyvalue.split()[1] for keyvalue in re.findall(
            r'<([^<>]*)>',
            " ".join(lstring)
        )}

        color = tags.get('bgcolor')
        if color:
            speaker_name = self.caption_color_to_speaker.get(color)
            if speaker_name is None:
                log.info(f'Color {color} has no associated speaker')
            else:
                self.caption_speaker = speaker_name

        for indicator, speaker in CAPTION_SPEAKER_INDICATORS:
            if indicator in dialog:
                log.info(f'Caption speaker identified: {speaker}')
                self.caption_speaker = speaker
                if color:
                    #INFO     cnv.chatlog.npc_chatter: Caption speaker identified: Positron                                                                             npc_chatter.py:401
                    #INFO     cnv.chatlog.npc_chatter: Assigning speaker Positron to color DarkGreen                      
                    log.info(f'Assigning speaker {speaker} to color {color}')
                    self.caption_color_to_speaker[color] = speaker
            #else:
            #    log.info(f'{indicator} is not in {dialog}')
        
        return self.caption_speaker, dialog

    def channel_messager(self, lstring, line_string: str):
        """
        All we know is that line_string starts with a [
        """
        # channel message
        dialog = line_string.strip()
        if ']' in dialog:
            close_bracket_index = dialog.find(']')
            channel = dialog[1: close_bracket_index]
            dialog = dialog[close_bracket_index + 1:].strip()
        else:
            log.error('Malformed channel message: %s', line_string)
            return       
        
        guide = self.channel_guide.get(channel, None)
        if guide and guide['enabled']:
            # log.info('Applying channel guide %s', guide)
            # channel messages are _from_ someone, the parsers extract that.
            parser = getattr(self, guide['parser'])
            speaker, dialog = parser(lstring)
            if dialog:
                console.log(f"\\[{channel}] {speaker}: " + colorstring(dialog))
            else:
                log.debug('Invalid lstring has no dialog: %s', lstring)

            # sometimes people don't say anything we can vocalize, like "..." so we drop any
            # non-dialog messages.
            if speaker not in ['__self__'] and dialog and dialog.strip():
                # log.info(f"Speaking: [{channel}] {speaker}: {dialog}")
                # speaker name, spoken dialog, channel (npc, system, player)
                self.speaking_queue.put((speaker, dialog, guide['name']))
            else:
                log.debug('Not speaking: %s', lstring)

        elif guide is None:
            # long lines will wrap
            hints = (
                (
                    ('DFB', 'Death From Below'), 
                    '''DFB: Death From Below
BLUE lvl 1-20
Started by LFG menu option.
Four missions chained together ending in a fight against two Hydra monsters'''
                ),  (
                    ('posi 1', 'POSI1', 'Posi Pt 1', ' pos1 ', 'Positron Part 1'), 
                    '''posi 1: Positron Task Force Part 1
BLUE lvl 10-15
Started by Positron in Steel Canyon.
Five missions, ending in a fight inside city hall'''
                ), (
                    ('posi 2', 'POSI2', 'Posi Pt 2', 'Positron Part 2'), 
                    '''posi 2: Positron Task Force Part 2
BLUE lvl 11-16
Started by Positron in Steel Canyon.
Five missions, ending in a fight near faultline dam'''
                ), (
                    ('YIN', 'PYIN'), 
                    '''yin: Penelope Yin Task Force
BLUE lvl 20-25
Started by Penelope Yin in Independence Port.
Five missions, ending in a fight inside the Terra Volta reactor'''
                ), (
                    ('NUMI', ), 
                    '''NUMI: Numina Task Force
BLUE lvl 35-40
Started by Numina in Founder's Falls.
Includes a set of 14 "Defeat X in Location" tasks
Five missions, ending in a fight against Jurassik deep inside Eden'''
                ), (
                    ('SBB', ), 
                    '''SBB: Summer Blockbuster Double Feature
BLUE lvl 15-?
Started by LFG menu option.
The trial takes the form of a double feature, where characters play roles inside two segments: "The Casino Heist" and "Time Gladiator". The segments are shown in random order, and are accessed through doors to different theaters.'''
                ), (
                    ('AEON', ), 
                    '''AEON: Dr. Aeon Strike Force
RED lvl 35-50
Started by Dr. Aeon in Cap Au Diable
Seven major missions'''
                ), (
                    ('Moonfire', ), 
                    '''MOONFIRE: The Kheldian War
BLUE lvl 23-28
Started by Moonfire on Striga Isle
Seven major missions, ends in fight with Arakhn -- A Nictus AV'''
                ), (
                    ('Market Crash', ), 
                    '''MARKET CRASH: Market Crash Trial
BLUE/RED lvl 40-50
Started by Ada Wellington in Kallisti Wharf
Three missions and a purple recipe reward
Ends with an AV fight against Crimson Prototype Waves of Sky Raiders 
adds at 75%, 50% and 25% health
Destroy the force field generators first
'''
                ), (
                    ('TinPex', ), 
                    '''TINPEX: Tin Mage Mark II Task Force
BLUE/RED lvl 50
Started by Tin Mage Mark II in Rikti War Zone
Three missions, ends in fight against two Goliath War Walkers'''
                ), (
                    ('Manti', 'Manticore'), 
                    '''MANTI: Manticore Task Force
Following Countess Crey
BLUE lvl 30-35
Started by Manticore in Brickstown
Seven missions, ends in fight against AV Hopkins in Creys Folly'''
                ),  (
                    ('Citadel', ), 
                    '''CITADEL: Citadel Task Force
Citadel's Children
BLUE lvl 25-30
Started by Citadel on Talos Island
Ten missions, ends in fight against AV Vandal'''
                )

            )
            found = False
            #console.log(f"\\[{channel}] {speaker}: " + colorstring(dialog))
            # there is no guide enabled, so we aren't giong to _speak_ this
            # but we might as well make the display pretty.
            
            console.log(f"\\[{channel}] " + colorstring(dialog))
            
            for references, helptext in hints:
                if found:
                    break

                for reference in references:
                    if reference.upper() in dialog.upper():
                        narrow_console = Console(width=60)
                        narrow_console.print(Panel(helptext))
                        found = True
                        break
 
        else:
            log.debug(f'{guide=}')

    def ssay(self, msg):
         # as in system-say
         log.info('SPEAKING: %s', msg)
         self.speaking_queue.put((None, msg, "system"))

    def tail(self):
        """
        read any new lines that have arrives since we last read the file and
        process each of them.

        We're in a multiprocessing.Process() while True, so the expectation is
        that we aren't going anywhere.

        self.open_latest_log needs to return an open, read-able file handle.
        """
        log.info('tail() invoked')
        lstring = ""

        # New character selected
        self.ssay('Log file found')
        self.find_character_login()
        
        log.info('Clearing damage data')
        models.clear_damage()

        self.first_tail = True

        activity_count = 0
        with open(self.open_latest_log(), encoding="utf-8") as handle:
            while True:
                if self.first_tail:
                    log.info('Seeking to EOF')
                    handle.seek(0, io.SEEK_END)
                    self.first_tail = False

                if activity_count > 50:
                    log.debug('primary log evaluation loop')
                    activity_count = 0
                else:
                    activity_count += 1

                for line in handle:
                    # log.debug("line: '%s'", line)

                    if line.strip():
                        log.debug('Top of True')               
                        talking = True
                        
                        # peel off the datestr and timestr, these are only rarely useful to us.
                        try:
                            datestr, timestr, line_string = line.split(None, 2)
                            line_string = line_string.strip()
                        except ValueError:
                            continue

                        # log.info('line_string: %s', line_string)
                        try:
                            # removing "." was a bad idea
                            lstring = line_string.replace(".", "").strip().split()
                        except Exception as err:
                            log.error(err)
                            raise

                        # if the first word starts with [, it is a channel indicator.  Send this off to channel_messager and move on.
                        if lstring[0][0] == "[":
                            log.debug('Invoking channel_messager()')
                            self.channel_messager(lstring, line_string)
                            log.debug('Returned from channel_messager()')
                            continue

                        if lstring[0] == "You":
                            if self.hero and lstring[1] == "gain":
                                # You gain 104 experience and 36 influence.
                                # You gain 15 experience, work off 15 debt, and gain 14 influence.
                                # You gain 26 experience and work off 2,676 debt.
                                # You gain 70 experience.
                                # You gain 2 stacks of Blood Frenzy!
                                log.debug(lstring)
                                # You gain 250 influence.

                                inf_gain = None
                                xp_gain = None

                                for inftype in ["influence", "information"]:
                                    try:
                                        influence_index = lstring.index(inftype) - 1
                                        inf_gain = int(
                                            lstring[influence_index].replace(",", "")
                                        )
                                    except ValueError:
                                        pass

                                try:
                                    if 'experience' in lstring:
                                        xp_gain = lstring[lstring.index('experience') - 1]
                                    elif 'experience,' in lstring:
                                        xp_gain = lstring[lstring.index('experience,') - 1]

                                    if xp_gain:
                                        xp_gain = int(xp_gain.replace(",", ""))
                                except ValueError:
                                    pass                            

                                if inf_gain or xp_gain:
                                    if not settings.REPLAY or settings.XP_IN_REPLAY:
                                        log.debug(f"Awarding xp: {xp_gain} and inf: {inf_gain}")
                                        with models.db() as session:
                                            new_event = models.HeroStatEvent(
                                                hero_id=self.hero.id,
                                                event_time=datetime.strptime(
                                                    f"{datestr} {timestr}", "%Y-%m-%d %H:%M:%S"
                                                ),
                                                xp_gain=xp_gain,
                                                inf_gain=inf_gain,
                                            )
                                            session.add(new_event)
                                            session.commit()

                            if self.hero and lstring[1] == "hit":
                                # You hit Abomination with your Assassin's Psi Blade for 43.22 points of Psionic damage.
                                # You hit Zealot with your Bitter Ice Blast for 13088 points of Cold damage (SCOURGE)
                                # You hit Button Man Buckshot with your Dart Burst for 10.61 points of Lethal damage over time.
                                # You hit Arva with your Freeze Ray for 7.49 points of Cold damage over time (SCOURGE).
                                
                                m = re.fullmatch(
                                    r"You hit (?P<target>.*) with your (?P<power>.*) for (?P<damage>.*) points of (?P<damage_type>.*) damage( |\.)?(?P<DOT>[^\n\(\.A-Z]*)[^\nA-Z\(]*\(?(?P<special>[A-Z]*).*",
                                    " ".join(lstring)
                                )
                                if m:
                                    #target, power, damage, damagetype, special = m.groups()
                                    if m['special'] is None:
                                        special = ""
                                    else:
                                        special = m['special'].strip("() \t\n\r\x0b\x0c").title()

                                    d = models.Damage(
                                        hero_id=self.hero.id,
                                        target=m['target'],
                                        power=m['power'],
                                        damage=int(m['damage']),
                                        damage_type=m['damage_type'],
                                        special=special
                                    )
                                    
                                    with models.db() as session:
                                        session.add(d)
                                        session.commit()
                                else:
                                    # You hit Gravedigger Slammer with your Twilight Grasp reducing their damage and chance to hit and healing you and your allies!
                                    m = re.fullmatch(
                                        r"You hit (?P<target>.*) with your (?P<power>.*) reducing .*",
                                        " ".join(lstring)
                                    )
                                    if m:
                                        # nothing to record
                                        pass
                                    else:
                                        dialog = plainstring(" ".join(lstring))
                                        log.warning(f'hit failed regex: {dialog}')

                        if self.hero and lstring[0] == "MISSED":
                            # MISSED Mamba Blade!! Your Contaminated Strike power had a 95.00% chance to hit, you rolled a 95.29.
                            m = re.fullmatch(
                                r"MISSED (?P<target>.*)!! Your (?P<power>.*) power had a (?P<chance_to_hit>[0-9\.]*)% chance to hit, you rolled a (?P<roll>[0-9\.]*).",
                                " ".join(lstring)
                            )
                            if m:
                                target, power, change_to_hit, roll = m.groups()
                                
                                # Okay to tuck a "miss" in here?
                                d = models.Damage(
                                    hero_id=self.hero.id,
                                    target=target,
                                    power=power,
                                    damage=0,
                                    damage_type="",
                                    special=""
                                )
                                
                                with models.db() as session:
                                    session.add(d)
                                    session.commit()
                            else:
                                log.warning('String failed regex:\n%s' % " ".join(lstring))

                        elif lstring[0] == "Welcome":
                            if self.hero:
                                # we've _changed_ characters.
                            
                                # Welcome to City of Heroes, <HERO NAME>
                                hero_name = " ".join(lstring[5:]).strip("!")
                                if hero_name != self.hero.name:
                                    self.hero = Hero(hero_name)

                                    # we want to notify upstream UI about this.
                                    self.event_queue.put(("SET_CHARACTER", self.hero.name))
                            else:
                                # I don't think this is a possible code path
                                # find_character_login should have already set self.hero()
                                self.hero = Hero(" ".join(lstring[5:]).strip("!"))

                        elif lstring[-2:] == ["is", "recharged"]:

                            log.debug('Adding RECHARGED event to event_queue...')
                            self.event_queue.put(
                                ("RECHARGED", " ".join(lstring[0:lstring.index("is")]))
                            )

                            # how long ago did this power last recharge?
                            power_name = " ".join(lstring[0:-2])
                            if power_name in self.previous_stopwatch:
                                dur_h, dur_m, dur_s = self.previous_stopwatch[power_name].split(':')
                                this_h, this_m, this_s = timestr.split(':')

                                h, m, s = (
                                    int(this_h) - int(dur_h),
                                    int(this_m) - int(dur_m),
                                    int(this_s) - int(dur_s)
                                )

                                total_seconds = (s + (m * 60) + (h * 3600))
                                # if this is a power we don't use very often, it's more likely we're interested in knowing when
                                # it recharges.  Two minutes feels about right to me.

                                if total_seconds >= (2 * 60):  # two minutes
                                    # only speak it if it took more than a minute
                                    if settings.get_toggle(settings.taggify('Speak Recharges')):
                                        dialog = plainstring(
                                            f"{power_name} recharged"
                                        )
                                        self.ssay(dialog)

                            self.previous_stopwatch[power_name] = timestr
                     
                        else:
                            prefix = lstring[0]
                            remainder = " ".join(lstring[1:])
                            done = False
                            if prefix in ['Ember', 'Cold', 'Fiery']:
                                continue

                            log.debug('Looking for prefix: %s', prefix)
                            if prefix in patterns.get_prefixes():
                                all_patterns = patterns.get_patterns(prefix)

                                log.debug('Checking for matches against %s patterns', len(all_patterns))
                                for pattern in all_patterns:
                                    m = pattern['compiled'].match(remainder)
                                    if m:
                                        log.debug('Match Found: %s', m)
                                        if pattern['enabled']:
                                            if settings.get_toggle(settings.taggify(pattern['toggle'])):
                                                if pattern.get('state'):
                                                    # this will update state.json, it's used for things like tracking
                                                    # the character level.
                                                    settings.set_config_key(
                                                        pattern['state'], m.group(1), cf='state.json'
                                                    )

                                                if pattern.get('strip_number', False):
                                                    # Removing the actual number makes the audio cache _many_ times more efficient.
                                                    # You are healed by your Dehydrate for 23.04 health points over time.
                                                    remainder = re.sub(r"for [0-9]+\.?[0-9]+ .*", "", remainder)

                                                talking = True
                                                if pattern.get('soak', 0) > 0:
                                                    soak_key = f"{prefix}_{pattern['regex']}"
                                                    # if we have a soak, we need to
                                                    # make sure at least than many
                                                    # seconds have passed since we
                                                    # last spoke this pattern
                                
                                                    h, m, s = timestr.split(':')
                                                    total_seconds = (int(h) * 3600) + (int(m) * 60) + int(s)

                                                    if (
                                                        soak_key in self.previous_stopwatch and
                                                        total_seconds - self.previous_stopwatch[soak_key] < pattern['soak']
                                                    ):
                                                        log.debug(f'Soaking {soak_key} for {pattern["soak"]} seconds')
                                                        talking = False
                                                    else:
                                                        self.previous_stopwatch[soak_key] = total_seconds

                                                if talking:
                                                    if pattern.get('append'):
                                                        # throw some flavor at the end.
                                                        dialog = plainstring(prefix + " " + remainder + " " + random.choice(pattern['append']))
                                                    else:
                                                        dialog = plainstring(prefix + " " + remainder)

                                                    # log.info('Pattern %s/%s matched.  Speaking %s', prefix, pattern['regex'], dialog)
                                                    self.ssay(dialog)
                                                else:
                                                    log.debug('Talking disabled')
                                            else:
                                                log.info('Toggle %s is not turned on', pattern['toggle'])
                                        else:
                                            log.debug('Pattern disabled')
                                        # we are done with the for pattern loop
                                        done = True
                                        break
                                    else:
                                        log.debug('Match failed: re.match("%s", "%s")', pattern['regex'], remainder)

                                if done:
                                    continue
                                else:
                                    log.debug('No matching patterns found for prefix: %s', prefix)

                            else:
                                # Check for global patterns (empty string)
                                all_patterns = patterns.get_patterns("")

                                log.debug('Checking to match %s against %s global patterns', remainder, len(all_patterns))
                                # TODO refactor to remove this redundancy
                                for pattern in all_patterns:
                                    m = pattern['compiled'].match(remainder)
                                    if m:
                                        log.debug('Match Found: %s', m)
                                        if pattern['enabled']:
                                            if settings.get_toggle(settings.taggify(pattern['toggle'])):
                                                if pattern.get('state'):
                                                    # this will update state.json, it's used for things like tracking
                                                    # the character level.
                                                    settings.set_config_key(
                                                        pattern['state'], m.group(1), cf='state.json'
                                                    )

                                                if pattern.get('strip_number', False):
                                                    # Removing the actual number makes the audio cache _many_ times more efficient.
                                                    # You are healed by your Dehydrate for 23.04 health points over time.
                                                    remainder = re.sub(r"for [0-9]+.*", "", remainder)

                                                talking = True
                                                if pattern.get('soak', 0) > 0:
                                                    soak_key = f"{prefix}_{pattern['regex']}"
                                                    # if we have a soak, we need to
                                                    # make sure at least than many
                                                    # seconds have passed since we
                                                    # last spoke this pattern
                                
                                                    h, m, s = timestr.split(':')
                                                    total_seconds = (int(h) * 3600) + (int(m) * 60) + int(s)

                                                    if (
                                                        soak_key in self.previous_stopwatch and
                                                        total_seconds - self.previous_stopwatch[soak_key] < pattern['soak']
                                                    ):
                                                        log.debug(f'Soaking {soak_key} for {pattern["soak"]} seconds')
                                                        talking = False
                                                    else:
                                                        self.previous_stopwatch[soak_key] = total_seconds

                                                if talking:
                                                    if pattern.get('append'):
                                                        # throw some flavor at the end.
                                                        dialog = plainstring(prefix + " " + remainder + " " + random.choice(pattern['append']))
                                                    else:
                                                        dialog = plainstring(prefix + " " + remainder)

                                                    log.info('Pattern %s/%s matched.  Speaking %s', prefix, pattern['regex'], dialog)
                                                    self.ssay(dialog)
                                                else:
                                                    log.info('Talking disabled')
                                            else:
                                                log.info('Toggle %s is not turned on', pattern['toggle'])
                                        else:
                                            log.info('Pattern disabled')
                                        # we are done with the for pattern loop
                                        done = True
                                        break
                                    else:
                                        log.debug('Global match failed: re.match("%s", "%s")', pattern['regex'], remainder)

                                if done:
                                    continue
                                else:
                                    log.debug('No matching global patterns found for: %s', remainder)

                        #
                        # Team task completed.
                        # A new team task has been chosen.                           
            
                # we've exhausted to EOF
                time.sleep(0.25)



class LogStream_old:
    """
    This is a streaming processor for the log file.  Its kind of sorely
    deficient in more than one way but seems to be at least barely adequate.
    """
    
    # if we don't get any new lines in this many seconds, double check to make
    # sure we're actually reading the most recent log file.  I think a float
    # would work here too.
    READ_TIMEOUT = 60
    previous_stopwatch = {}
    previous_darkest = 0

    # what channels are we paying attention to, which self.parser function is
    # going to be called to properly extract the data from that log entry.
    channel_guide = {
        'NPC': {
            'enabled': True,
            'name': "npc",
            'parser': 'channel_chat_parser'
        },
        'Team': {
            'enabled': True,
            'name': "player",
            'parser': 'channel_chat_parser'
        },
        'Tell': {
            'enabled': True,
            'name': "player",
            'parser': 'tell_chat_parser'
        },
        'Caption': {
            'enabled': True,
            'name': "npc",
            'parser': 'caption_parser'
        }
    }

    def __init__(
        self,
        logdir: str,
        speaking_queue: queue.Queue,
        event_queue: queue.Queue,
        badges: bool,
        npc: bool,
        team: bool,
    ):
        """
        find the most recent logfile in logdir note which file it is, open it,
        do a light scan to find the beginning of the current characters session.
        There is some character data there we need. Then we skip to the end and
        start tailing.
        """
        self.logdir = logdir
        self.announce_badges = badges
        # TODO: these should be exposed on the configuration page
        self.npc_speak = npc
        self.team_speak = team
        self.tell_speak = True
        self.caption_speak = True
        self.announce_levels = True
        self.hero = None
        # who is (as far as we know) currently speaking as CAPTION ?
        self.caption_speaker = None
        self.caption_color_to_speaker = {}

        # carry these along for I/O
        self.speaking_queue = speaking_queue
        self.event_queue = event_queue

        self.logfile = None
        self.first_tail = True
        log.debug(f'(init) Setting {self.logfile=}')

    def open_latest_log(self):
        all_files = glob.glob(os.path.join(self.logdir, "*.txt"))
        filename = max(all_files, key=os.path.getctime)
        
        log.info(f'(oll) Setting {self.logfile=} = {filename}')
        self.logfile = filename
        return os.path.join(self.logdir, filename)

    def find_character_login(self):
        """0
        Skim through and see if can find the beginning of the current characters
        login.
        """
        hero_name = None
        log.info('find_character_login()')
        # we want the most recent entries of specific strings. This might be
        # better done backwards
        # ,
        #    "r",
        #    encoding="utf-8",
        #)
        with open(self.open_latest_log(), 'r', encoding="utf-8") as handle:
            log.info('Searching for welcome message')
            for line in handle:
                try:
                    datestr, timestr, line_string = line.split(None, 2)
                except ValueError:
                    continue

                lstring = line_string.split()
                
                if lstring[0] == "Welcome":
                    # Welcome to City of Heroes, <HERO NAME>
                    self.is_hero = True
                    hero_name = " ".join(lstring[5:]).strip("!")
                    # we want to notify upstream UI about this.
                elif lstring[0:5] == ["Now", "entering", "the", "Rogue", "Isles,"]:
                    # 2024-04-17 17:10:27 Now entering the Rogue Isles, Kim Chee!
                    self.is_hero = False
                    hero_name = " ".join(lstring[5:]).strip("!")
                
                if hero_name:
                    break
                else:
                    log.info(lstring)

        log.info("hero_name: %s", hero_name)
        if hero_name:
            self.hero = Hero(hero_name)
            
            if self.event_queue:
                self.event_queue.put(("SET_CHARACTER", self.hero.name))

            if not settings.REPLAY:
                send_log_lock()
                log.info('log_lock attached')

        else:
            self.ssay("User name not detected")
            log.warning("Could NOT find hero name.. good luck.")

    def channel_chat_parser(self, lstring):
        speaker, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
        dialog = plainstring(dialog)
        return speaker, dialog

    def tell_chat_parser(self, lstring):
        """
        Who is talking, what are they saying?
        """
        # why is there an extra colon for Tell?  IDK.        
        if lstring[1][:3] == "-->":
            # note: target names with spaces are not parsed
            # ["[Tell]", "-->Toxic", "Timber:", "pls"]
            # this is a reply to a tell, or an outbound tell.

            # these are self-tells so we have to catch both of them, but we only
            # need to process one of them.  For no particular reason
            # we're going to use the --> inbound message.

            # [Tell] :Ghlorius: [SIDEKICK] name="Ghlorius" 
            # [Tell] -->Ghlorius: [SIDEKICK] name="Ghlorius"
            dialog = (
                " ".join(lstring[1:]).split(":", maxsplit=1)[-1].strip()
            )

            if dialog.split()[0] == "[SIDEKICK]":
                log.info('Parsing SIDEKICK')
                # player attribute self-reporting
                # key=value;key2=value2
                _, all_keyvals = dialog.split(None, maxsplit=1)

                for keyvalue in all_keyvals.split(';'):
                    try:
                        key, value = keyvalue.strip().split('=')
                    except ValueError:
                        log.warning(f'Invalid SIDEKICK: {dialog}')
                        return "__self__", None    

                    settings.set_config_key(
                        key, 
                        value.strip('"'),
                        cf='state.json'
                    )

                # don't try and speak it.
                return "__self__", None

            speaker = "__self__"
        else:
            # ["[Tell]", ":Dressy Bessie:", "I", "can", "bump", "you"]
            # ["[Tell]", ":StoneRipper:", "it:s", "underneath"]
            speaker = None
            dialog = None
            try:
                # ["", "Dressy Bessie", "I can bump you"]
                # ['', 'StoneRipper', ' it:s underneath']
                full_string = " ".join(lstring[1:])

                if ':' in full_string:
                    _, speaker, dialog = full_string.split(
                        ":", maxsplit=2
                    )
                    # ignore SIDEKICK self-tells 
                    try:
                        if dialog.split()[0] == "[SIDEKICK]":
                            return "__self__", None
                    except IndexError:
                        pass

            except ValueError:
                # 2024-07-27 17:17:07 [Tell] You are banned from talking for 2 minutes, 0 seconds.
                # logging at info so I can maybe catch it in the future.
                log.info(f'1 ADD DOC: {lstring=}')
                speaker, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
        
        dialog = plainstring(dialog)
        return speaker, dialog

    def caption_parser(self, lstring):
        """
        Caption messages are a liitle.. fun.  Usually the first message from a
        given speaker identifies the speaker by name but subsequent messages do
        not.  They do consistently use the same background color for each
        speaker.  So we notice when a named speaker introduces themselves then
        we associate that bgcolor with that speaker so we can use the same
        voice.

        A good test for this is the back and forth dialog between Dana and
        Matthew.

        The key data here are the strings in CAPTION_SPEAKER_INDICATORS linking
        introduction messages to speakers.  It will need to be significantly
        expanded to cover more 'caption' speakers.
        """
        # [Caption] <scalxe 2.75><color red><bgcolor White>My Shadow Simulacrum will destroy Task Force White Sands!
        # [Caption] <scale 1.75><color white><bgcolor DarkGreen>Positron here. I'm monitoring your current progress in the sewers. 
        log.debug(f'CAPTION: {lstring}')
        dialog = plainstring(" ".join(lstring[1:]))
        dialog = dialog.replace('*', '')  # the stupid TTS engine say "asterisk" and it is tediously dumb.

        # make an effort to identify the speaker
        # Positron here. I'm monitoring your current progress in the sewers.
        tags = {keyvalue.split()[0]: keyvalue.split()[1] for keyvalue in re.findall(
            r'<([^<>]*)>',
            " ".join(lstring)
        )}

        color = tags.get('bgcolor')
        if color:
            speaker_name = self.caption_color_to_speaker.get(color)
            if speaker_name is None:
                log.info(f'Color {color} has no associated speaker')
            else:
                self.caption_speaker = speaker_name

        for indicator, speaker in CAPTION_SPEAKER_INDICATORS:
            if indicator in dialog:
                log.info(f'Caption speaker identified: {speaker}')
                self.caption_speaker = speaker
                if color:
                    #INFO     cnv.chatlog.npc_chatter: Caption speaker identified: Positron                                                                             npc_chatter.py:401
                    #INFO     cnv.chatlog.npc_chatter: Assigning speaker Positron to color DarkGreen                      
                    log.info(f'Assigning speaker {speaker} to color {color}')
                    self.caption_color_to_speaker[color] = speaker
            #else:
            #    log.info(f'{indicator} is not in {dialog}')
        
        return self.caption_speaker, dialog

    def channel_messager(self, lstring, line_string: str):
        """
        All we know is that line_string starts with a [
        """
        # channel message
        dialog = line_string.strip()
        if ']' in dialog:
            close_bracket_index = dialog.find(']')
            channel = dialog[1: close_bracket_index]
            dialog = dialog[close_bracket_index + 1:].strip()
        else:
            log.error('Malformed channel message: %s', line_string)
            return       
        
        guide = self.channel_guide.get(channel, None)
        if guide and guide['enabled']:
            # log.info('Applying channel guide %s', guide)
            # channel messages are _from_ someone, the parsers extract that.
            parser = getattr(self, guide['parser'])
            speaker, dialog = parser(lstring)
            if dialog:
                console.log(f"\\[{channel}] {speaker}: " + colorstring(dialog))
            else:
                log.debug('Invalid lstring has no dialog: %s', lstring)

            # sometimes people don't say anything we can vocalize, like "..." so we drop any
            # non-dialog messages.
            if speaker not in ['__self__'] and dialog and dialog.strip():
                # log.info(f"Speaking: [{channel}] {speaker}: {dialog}")
                # speaker name, spoken dialog, channel (npc, system, player)
                self.speaking_queue.put((speaker, dialog, guide['name']))
            else:
                log.debug('Not speaking: %s', lstring)

        elif guide is None:
            # long lines will wrap
            hints = (
                (
                    ('DFB', 'Death From Below'), 
                    '''DFB: Death From Below
BLUE lvl 1-20
Started by LFG menu option.
Four missions chained together ending in a fight against two Hydra monsters'''
                ),  (
                    ('posi 1', 'POSI1', 'Posi Pt 1', ' pos1 ', 'Positron Part 1'), 
                    '''posi 1: Positron Task Force Part 1
BLUE lvl 10-15
Started by Positron in Steel Canyon.
Five missions, ending in a fight inside city hall'''
                ), (
                    ('posi 2', 'POSI2', 'Posi Pt 2', 'Positron Part 2'), 
                    '''posi 2: Positron Task Force Part 2
BLUE lvl 11-16
Started by Positron in Steel Canyon.
Five missions, ending in a fight near faultline dam'''
                ), (
                    ('YIN', 'PYIN'), 
                    '''yin: Penelope Yin Task Force
BLUE lvl 20-25
Started by Penelope Yin in Independence Port.
Five missions, ending in a fight inside the Terra Volta reactor'''
                ), (
                    ('NUMI', ), 
                    '''NUMI: Numina Task Force
BLUE lvl 35-40
Started by Numina in Founder's Falls.
Includes a set of 14 "Defeat X in Location" tasks
Five missions, ending in a fight against Jurassik deep inside Eden'''
                ), (
                    ('SBB', ), 
                    '''SBB: Summer Blockbuster Double Feature
BLUE lvl 15-?
Started by LFG menu option.
The trial takes the form of a double feature, where characters play roles inside two segments: "The Casino Heist" and "Time Gladiator". The segments are shown in random order, and are accessed through doors to different theaters.'''
                ), (
                    ('AEON', ), 
                    '''AEON: Dr. Aeon Strike Force
RED lvl 35-50
Started by Dr. Aeon in Cap Au Diable
Seven major missions'''
                ), (
                    ('Moonfire', ), 
                    '''MOONFIRE: The Kheldian War
BLUE lvl 23-28
Started by Moonfire on Striga Isle
Seven major missions, ends in fight with Arakhn -- A Nictus AV'''
                ), (
                    ('Market Crash', ), 
                    '''MARKET CRASH: Market Crash Trial
BLUE/RED lvl 40-50
Started by Ada Wellington in Kallisti Wharf
Three missions and a purple recipe reward
Ends with an AV fight against Crimson Prototype Waves of Sky Raiders 
adds at 75%, 50% and 25% health
Destroy the force field generators first
'''
                ), (
                    ('TinPex', ), 
                    '''TINPEX: Tin Mage Mark II Task Force
BLUE/RED lvl 50
Started by Tin Mage Mark II in Rikti War Zone
Three missions, ends in fight against two Goliath War Walkers'''
                ), (
                    ('Manti', 'Manticore'), 
                    '''MANTI: Manticore Task Force
Following Countess Crey
BLUE lvl 30-35
Started by Manticore in Brickstown
Seven missions, ends in fight against AV Hopkins in Creys Folly'''
                ),  (
                    ('Citadel', ), 
                    '''CITADEL: Citadel Task Force
Citadel's Children
BLUE lvl 25-30
Started by Citadel on Talos Island
Ten missions, ends in fight against AV Vandal'''
                )

            )
            found = False
            #console.log(f"\\[{channel}] {speaker}: " + colorstring(dialog))
            # there is no guide enabled, so we aren't giong to _speak_ this
            # but we might as well make the display pretty.
            
            console.log(f"\\[{channel}] " + colorstring(dialog))
            
            for references, helptext in hints:
                if found:
                    break

                for reference in references:
                    if reference.upper() in dialog.upper():
                        narrow_console = Console(width=60)
                        narrow_console.print(Panel(helptext))
                        found = True
                        break
 
        else:
            log.debug(f'{guide=}')

    def ssay(self, msg):
         # as in system-say
         log.info('SPEAKING: %s', msg)
         self.speaking_queue.put((None, msg, "system"))

    def tail(self):
        """
        read any new lines that have arrives since we last read the file and
        process each of them.

        We're in a multiprocessing.Process() while True, so the expectation is
        that we aren't going anywhere.

        self.open_latest_log needs to return an open, read-able file handle.
        """
        log.info('tail() invoked')
        lstring = ""

        # New character selected
        self.ssay('Log file found')
        self.find_character_login()
        
        log.info('Clearing damage data')
        models.clear_damage()

        self.first_tail = True

        activity_count = 0
        with open(self.open_latest_log(), encoding="utf-8") as handle:
            while True:
                if self.first_tail:
                    log.info('Seeking to EOF')
                    handle.seek(0, io.SEEK_END)
                    self.first_tail = False

                if activity_count > 50:
                    log.debug('primary log evaluation loop')
                    activity_count = 0
                else:
                    activity_count += 1

                for line in handle:
                    # log.debug("line: '%s'", line)

                    if line.strip():
                        log.debug('Top of True')               
                        talking = True
                        
                        try:
                            datestr, timestr, line_string = line.split(None, 2)
                            line_string = line_string.strip()
                        except ValueError:
                            # log.error('Invalid line.split(%s)', line)
                            continue

                        # log.info('line_string: %s', line_string)
                        try:
                            lstring = line_string.replace(".", "").strip().split()
                            # "['Hasten', 'is', 'recharged']" 
                            # log.info("lstring: %s", lstring)
                        except Exception as err:
                            log.error(err)
                            raise

                        if lstring[0][0] == "[":
                            log.debug('Invoking channel_messager()')
                            self.channel_messager(lstring, line_string)
                            log.debug('Returned from channel_messager()')
                            continue

                        elif self.announce_badges and lstring[0] == "Congratulations!":
                            self.ssay(" ".join(lstring[4:]))

                        elif lstring[0] == "You":
                            log.debug('"You" path')
                            if lstring[1] in ["stopped", "found", "stole", "begin", "finished", "open", "didn't", "rescued"]:
                                # You stopped the Superadine shipment and arrested Chernobog Petrovic, one of the Skulls' founders!
                                # You found a face mask that is covered in some kind of mold. It appears to be pulsing like it's breathing. You send a short video to Watkins for evidence.
                                # You have cleared the Snakes from the Arachnos base, and learned something interesting.
                                # You stole the money!
                                # You finished searching through the records
                                # You didn't find Percy's Record
                                # You open the records and find it filled with wooden tubes studded with holes. As you pick one up it emits a verbal record of the individual it is about.
                                dialog = plainstring(" ".join(lstring))
                                if talking:
                                    self.ssay(dialog)

                            elif lstring[1] == "have":
                                enabled = False
                                # have is tricky.  lots of things use have.
                                dialog = plainstring(" ".join(lstring))
                                if lstring[2] == "defeated":
                                    enabled = settings.get_toggle(settings.taggify("Acknowledge each win"))

                                    if talking and enabled:
                                        self.ssay(dialog)
                                    else:
                                        log.info(f'Not speaking: {talking=} {enabled=}')

                                elif lstring[2] in ["Insight", "Uncanny"]:
                                    # You have Insight into your enemy's weaknesses and slightly increase your chance To Hit and your Perception.
                                    pass

                                elif lstring[2] == "been":
                                    enabled =False
                                    # buffs and debuffs
                                    if lstring[3] in [
                                        "put", "immobilized!", "exemplared", 
                                        "interrupted.", "held", "temporarily",
                                        "blinded"
                                    ]:
                                        enabled = settings.get_toggle(settings.taggify('Speak Debuffs'))
                                    elif lstring[3] in ["granted", ]:
                                        enabled = settings.get_toggle(settings.taggify('Speak Buffs'))

                                    if talking and enabled:
                                        self.ssay(dialog)

                                elif lstring[3] == "unclaimed":
                                    # respects and tailer sessions
                                    
                                    # You have 3 unclaimed respecs available Type /respec in the chat window to begin respecing your character
                                    # respects is too wordy, takes too long to say and happens on every login.  cut it down.
                                    if lstring[4] == "respecs":
                                        dialog = plainstring(" ".join(lstring[:6]))
                                    
                                    # this one is less annoying.
                                    # You have 3 unclaimed free tailor sessions available.
                                    self.ssay(dialog)

                                elif talking:
                                    self.ssay(dialog)

                            elif lstring[1] == "are":
                                enabled = False
                                if lstring[2] in ['held!', 'unable']:
                                    # 2024-04-01 20:04:17 You are held!
                                    enabled = settings.get_toggle(settings.taggify('Speak Debuffs'))
                                elif lstring[2] in ['healed', 'filled', 'now', 'Robust', 'Enraged', 'hidden', 'Sturdy']:
                                    log.debug(f'You are: {lstring}')
                                    enabled = settings.get_toggle(settings.taggify('Speak Buffs'))
                                    #  You are healed by your Dehydrate for 23.04 health points over time.
                                    if lstring[2] == "healed" and lstring[3:5] == ["by", "your"]:
                                        if lstring[5:7] == ['Defensive', 'Adaptation']:
                                            # Way, way too verbose.
                                            enabled = False
                                            
                                        # don't speak the exact numbers, it destroyed the voice cache
                                        lstring = lstring[:lstring.index('for')]
                                        log.debug(f'Trimming lstring to {lstring}')
                                    else:
                                        log.debug(f'lstring[2]={lstring[2]} and {lstring[3:5]}')

                                if talking and enabled:
                                    dialog = plainstring(" ".join(lstring))
                                    self.ssay(dialog)

                            elif self.hero and lstring[1] == "gain":
                                # You gain 104 experience and 36 influence.
                                # You gain 15 experience, work off 15 debt, and gain 14 influence.
                                # You gain 26 experience and work off 2,676 debt.
                                # You gain 70 experience.
                                # You gain 2 stacks of Blood Frenzy!
                                # I'm just going to make the database carry the burden, so much easier.
                                # is this string stable enough to get away with this?  It's friggin'
                                # cheating.
                                log.debug(lstring)
                                # You gain 250 influence.

                                inf_gain = None
                                xp_gain = None

                                for inftype in ["influence", "information"]:
                                    try:
                                        influence_index = lstring.index(inftype) - 1
                                        inf_gain = int(
                                            lstring[influence_index].replace(",", "")
                                        )
                                    except ValueError:
                                        pass

                                try:
                                    if 'experience' in lstring:
                                        xp_gain = lstring[lstring.index('experience') - 1]
                                    elif 'experience,' in lstring:
                                        xp_gain = lstring[lstring.index('experience,') - 1]

                                    if xp_gain:
                                        xp_gain = int(xp_gain.replace(",", ""))
                                except ValueError:
                                    pass                            

                                # try:
                                #     did_i_defeat_it = previous.index("defeated")
                                #     foe = " ".join(previous[did_i_defeat_it:])
                                # except ValueError:
                                #     # no, someone else did.  you just got some
                                #     # points for it.  Lazybones.
                                #     foe = None
                                
                                # we _could_ visualize the percentage of kills
                                # by each player in the party.
                                if inf_gain or xp_gain:
                                    if not settings.REPLAY or settings.XP_IN_REPLAY:
                                        log.debug(f"Awarding xp: {xp_gain} and inf: {inf_gain}")
                                        with models.db() as session:
                                            new_event = models.HeroStatEvent(
                                                hero_id=self.hero.id,
                                                event_time=datetime.strptime(
                                                    f"{datestr} {timestr}", "%Y-%m-%d %H:%M:%S"
                                                ),
                                                xp_gain=xp_gain,
                                                inf_gain=inf_gain,
                                            )
                                            session.add(new_event)
                                            session.commit()
                            if self.hero and lstring[1] == "hit":
                                # You hit Abomination with your Assassin's Psi Blade for 43.22 points of Psionic damage.
                                # You hit Zealot with your Bitter Ice Blast for 13088 points of Cold damage (SCOURGE)
                                # You hit Button Man Buckshot with your Dart Burst for 10.61 points of Lethal damage over time.
                                # You hit Arva with your Freeze Ray for 7.49 points of Cold damage over time (SCOURGE).
                                
                                m = re.fullmatch(
                                    r"You hit (?P<target>.*) with your (?P<power>.*) for (?P<damage>.*) points of (?P<damage_type>.*) damage( |\.)?(?P<DOT>[^\n\(\.A-Z]*)[^\nA-Z\(]*\(?(?P<special>[A-Z]*).*",
                                    " ".join(lstring)
                                )
                                if m:
                                    #target, power, damage, damagetype, special = m.groups()
                                    if m['special'] is None:
                                        special = ""
                                    else:
                                        special = m['special'].strip("() \t\n\r\x0b\x0c").title()

                                    d = models.Damage(
                                        hero_id=self.hero.id,
                                        target=m['target'],
                                        power=m['power'],
                                        damage=int(m['damage']),
                                        damage_type=m['damage_type'],
                                        special=special
                                    )
                                    
                                    with models.db() as session:
                                        session.add(d)
                                        session.commit()
                                else:
                                    # You hit Gravedigger Slammer with your Twilight Grasp reducing their damage and chance to hit and healing you and your allies!
                                    m = re.fullmatch(
                                        r"You hit (?P<target>.*) with your (?P<power>.*) reducing .*",
                                        " ".join(lstring)
                                    )
                                    if m:
                                        # nothing to record
                                        pass
                                    else:
                                        dialog = plainstring(" ".join(lstring))
                                        log.warning(f'hit failed regex: {dialog}')

                            elif lstring[1] in ["carefully", "look", "find"]:
                                dialog = plainstring(" ".join(lstring))
                                self.speaking_queue.put((None, dialog, "system"))
                            
                            elif lstring[1] in ["activated", "Taunt"]:
                                # skip "You activated ..."
                                continue

                            elif lstring[1] == "received":
                                # You received 6 reward merits.
                                if lstring[-2:0] == ["reward", "merits."]:
                                    if settings.get_toggle(settings.taggify('Speak Merits')):
                                        dialog = plainstring(" ".join(lstring))
                                        self.ssay(dialog)

                                elif lstring[-1] == "(Recipe).":
                                    # You received Cacophony: Confuse/Range (Recipe).
                                    if settings.get_toggle(settings.taggify('Speak Recipes')):
                                        dialog = plainstring(" ".join(lstring))
                                        self.ssay(dialog)

                        elif self.hero and lstring[0] == "MISSED":
                            # MISSED Mamba Blade!! Your Contaminated Strike power had a 95.00% chance to hit, you rolled a 95.29.
                            m = re.fullmatch(
                                r"MISSED (?P<target>.*)!! Your (?P<power>.*) power had a (?P<chance_to_hit>[0-9\.]*)% chance to hit, you rolled a (?P<roll>[0-9\.]*).",
                                " ".join(lstring)
                            )
                            if m:
                                target, power, change_to_hit, roll = m.groups()
                                
                                # Okay to tuck a "miss" in here?
                                d = models.Damage(
                                    hero_id=self.hero.id,
                                    target=target,
                                    power=power,
                                    damage=0,
                                    damage_type="",
                                    special=""
                                )
                                
                                with models.db() as session:
                                    session.add(d)
                                    session.commit()
                            else:
                                log.warning('String failed regex:\n%s' % " ".join(lstring))

                        elif lstring[0] == "Welcome":
                            if self.hero:
                                # we've _changed_ characters.
                            
                                # Welcome to City of Heroes, <HERO NAME>
                                hero_name = " ".join(lstring[5:]).strip("!")
                                if hero_name != self.hero.name:
                                    self.hero = Hero(hero_name)

                                    # we want to notify upstream UI about this.
                                    self.event_queue.put(("SET_CHARACTER", self.hero.name))
                            else:
                                # I don't think this is a possible code path
                                # find_character_login should have already set self.hero()
                                self.hero = Hero(" ".join(lstring[5:]).strip("!"))

                        elif lstring[0] == "Entering" and lstring[-2:] == ["Medical", "Center"]:
                            # Entering Steel Canyon Medical Center.
                            if settings.get_toggle(settings.taggify('Snark')):
                                dialog = "Welcome back to " + plainstring(" ".join(lstring[1:]) + ".  Again.  Maybe you should buy an awaken or six.")
                                self.ssay(dialog)

                        elif lstring[-2:] == ["is", "recharged"]:

                            log.debug('Adding RECHARGED event to event_queue...')
                            self.event_queue.put(
                                ("RECHARGED", " ".join(lstring[0:lstring.index("is")]))
                            )

                            # how long ago did this power last recharge?
                            power_name = " ".join(lstring[0:-2])
                            if power_name in self.previous_stopwatch:
                                dur_h, dur_m, dur_s = self.previous_stopwatch[power_name].split(':')
                                this_h, this_m, this_s = timestr.split(':')

                                h, m, s = (
                                    int(this_h) - int(dur_h),
                                    int(this_m) - int(dur_m),
                                    int(this_s) - int(dur_s)
                                )

                                total_seconds = (s + (m * 60) + (h * 3600))
                                # if this is a power we don't use very often, it's more likely we're interested in knowing when
                                # it recharges.  Two minutes feels about right to me.

                                if total_seconds >= (2 * 60):  # two minutes
                                    # only speak it if it took more than a minute
                                    if settings.get_toggle(settings.taggify('Speak Recharges')):
                                        dialog = plainstring(
                                            f"{power_name} recharged"
                                        )
                                        self.ssay(dialog)

                            self.previous_stopwatch[power_name] = timestr

                        elif lstring[-2:] == ["the", "team"]:
                            name = " ".join(lstring[0:-4])
                            action = lstring[-3]  # joined or quit
                            if settings.get_toggle(settings.taggify('Team Changes')):
                                self.ssay(f"Player {name} has {action} the team")

                        elif lstring[:2] in ["The", "name", "The", "whiteboard"]:
                            # The name <color red>Toothbreaker Jones</color> keeps popping up, and these Skulls were nice enough to tell you where to find him. Time to pay him a visit.
                            dialog = plainstring(" ".join(lstring))
                            self.ssay(dialog)

                        elif lstring[0:2] == ["Your", "combat"]:
                            # 2024-07-26 19:01:05 Your combat improves to level 23! Seek a trainer to further your abilities.
                            level = int(lstring[5].strip('!'))
                            self.ssay(f"Congratulations.  You have reached Level {level}")
                            
                            # this will update the character tab
                            settings.set_config_key(
                            'level', level, cf='state.json'
                            )

                        elif lstring[0:3] == ["Your", "Siphon", "Speed"]:
                            # Your Siphon Speed has slowed the attack and movement speed of Prototype Oscillator while increasing your own!
                            if settings.get_toggle(settings.taggify('Speak Buffs')):
                                dialog = plainstring(" ".join(lstring))
                                self.ssay(dialog)

                        elif lstring[0:3] == ["Your", "Darkest", "Night"]:
                            # Your Darkest Night reduced the damage and chance to hit of Fallen Buckshot and all foes nearby.
                            h, m, s = timestr.split(':')
                            total_seconds = (int(h) * 3600) + (int(m) * 60) + int(s)

                            if total_seconds - self.previous_darkest >= DARKEST_SOAK:
                                if settings.get_toggle(settings.taggify('Speak Buffs')):
                                    dialog = plainstring("Darkest Night attached to " + " ".join(lstring[11:-4]))
                                    self.ssay(dialog)
                                    self.previous_darkest = total_seconds

                        elif lstring[0:4] == ["Shutting", "off", "Darkest", "Night"]:
                            # Shutting off Darkest Night.
                            if settings.get_toggle(settings.taggify('Speak Buffs')):
                                dialog = plainstring("Darkest Night detached")
                                self.ssay(dialog)

                        # single word things to speak, mostly clicky descriptions
                        elif lstring[0] in ["Something's", "In", "Jones", "This", "You've", "Where"]:
                            # Something's not right with this spot on the floor...
                            # This blotch of petroleum on the ground seems fresh, perhaps leaked by a 'zoombie' and a sign that they're near. You take a photo and send it to Watkins.
                            # You've found a photocopy of a highly detailed page from a medical notebook, with wildly complex notes about cybernetics. 
                            dialog = plainstring(" ".join(lstring))
                            if (settings.REPLAY and settings.SPEECH_IN_REPLAY) or not settings.REPLAY:
                                self.ssay(dialog)

                        elif len(lstring) >= 6 and lstring[-6:] == ["boosts", "the", "damage", "of", "your", "attacks!"]:
                            # siphon power
                            # The Just Chillin' boosts the damage of your attacks!
                            if settings.get_toggle(settings.taggify('Speak Buffs')):
                                dialog = plainstring(" ".join(lstring[1:]))  # This one is buggy, adds a "The" to the beginning.
                                self.ssay(dialog)

                        elif lstring[0] == "The":
                            if lstring[1] in ["bottom", "whiteboard", ]:
                                # The bottom of this empty box..
                                # The whiteboard appears to be...
                                dialog = plainstring(" ".join(lstring))
                                self.ssay(dialog)

                        elif len(lstring) >= 6 and lstring[-6:-4] == ['Twilight', 'Grasp']:
                            # Old McFahrty heals you with their Twilight Grasp for 22.02 health points.
                            if settings.get_toggle(settings.taggify('Speak Buffs')):
                                dialog = plainstring(" ".join(lstring[:-4]))
                                self.ssay(dialog)

                        elif len(lstring) >= 9 and lstring[-9:-4] == ['heals', 'you', 'with', 'their', 'Transfusion']:
                            # Just Chillin' heals you with their Transfusion for 92.22 health points.
                            if settings.get_toggle(settings.taggify('Speak Buffs')):
                                dialog = plainstring(" ".join(lstring[:-4]))
                                self.ssay(dialog)                        
                        else:
                            log.debug(f'tag "{lstring}" not classified.')
                            continue
                        #
                        # Team task completed.
                        # A new team task has been chosen.                           
            
                # we've exhausted to EOF
                time.sleep(0.25)


class Hero:
    # keep this update for cheap parlor tricks.
    columns = (
        "id",
        "name",
    )

    def __init__(self, hero_name):
        self.name = hero_name
        self.load_hero(hero_name)

    def load_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = session.query(models.Hero).filter_by(name=hero_name).first()

        if hero is None:
            return self.create_hero(hero_name)

        self.id = hero.id
        
        for c in self.columns:
            setattr(self, c, getattr(hero, c))

    def create_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = models.Hero(name=hero_name)
            session.add(hero)
            session.commit()

        # this is a disaster waiting to happen.
        return self.load_hero(hero_name)
