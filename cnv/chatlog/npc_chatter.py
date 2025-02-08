import argparse
import glob
import io
import logging
import os
import queue
import re
import voicebox
import threading
import time
from datetime import datetime

import cnv.database.models as models
import cnv.logger
import cnv.voices.voice_builder as voice_builder
import lib.settings as settings
import simpleaudio
import pythoncom
# import voicebox
from cnv.lib.proc import send_log_lock
from pedalboard.io import AudioFile
from voicebox.tts.utils import get_audio_from_wav_file

cnv.logger.init()
log = logging.getLogger(__name__)

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
    ('This is Robert Alderman', 'Robert Alderman')
)

# class ParallelTTS(threading.Thread):
#     def __init__(self, speaking_queue, event_queue, parallelism=2):
#         """
#         parallelism > 2 seems to be pretty unstable.  This is fun, but essentially wrong.  What
#         happens when the same character says two things one right after the other?  Yes, they talk
#         on top of themselves.
#         """
#         threading.Thread.__init__(self)
#         self.speaking_queue = speaking_queue
#         self.event_queue = event_queue
#         self.daemon = True
#         self.parallelism = parallelism

#         # so we can do this much once.
#         for category in ["npc", "player", "system"]:
#             for dir in [
#                 os.path.join("clip_library"),
#                 os.path.join("clip_library", category),
#             ]:
#                 try:
#                     os.mkdir(dir)
#                 except OSError:
#                     # the directory already exists.  This is not a problem.
#                     pass

#         self.start()

#     def playfile(self, cachefile):
#         log.info(f"Cache Hit: {cachefile}")
#         audio_obj = audio.mp3file_to_Audio(cachefile)
#         voicebox.sinks.SoundDevice().play(audio_obj)

#     def pluck_and_speak(self, name, message, category):
#         # to get the cachefile, we need the right message.
#         # to get the right message it needs to be translated
#         # to be translated it needs to be a phrase; 
#         phrase_id = models.get_or_create_phrase_id(name, category, message)

#         # translate if it needs to be translated.
#         message = models.get_translated(phrase_id)

#         # determine its cold storage filename
#         cachefile = settings.get_cachefile(name, message, category)
        
#         try:
#             os.mkdir(os.path.dirname(cachefile))
#         except OSError:
#             # the directory already exists.  This is not a problem.
#             pass

#         with models.db() as session:
#             character = models.Character.get(name, category, session)

#             if os.path.exists(cachefile):
#                 self.playfile(cachefile)
#             else:
#                 voice_builder.create(
#                     character=character,
#                     message=message,
#                     session=session
#                 )

#             models.update_character_last_spoke(character, session)

#         self.event_queue.put(
#             ("SPOKE", (character.name, character.category))
#         )

#         self.speaking_queue.task_done()

#     def run(self):
#         pythoncom.CoInitialize()

#         with concurrent.futures.ThreadPoolExecutor(
#             max_workers=self.parallelism
#         ) as executor:
#             while True:
#                 raw_message = self.speaking_queue.get()
#                 try:
#                     name, message, category = raw_message
#                     if category not in ["npc", "player", "system"]:
#                         log.error("invalid category: %s", category)
#                     else:
#                         executor.submit(self.pluck_and_speak, name, message, category)
#                 except ValueError:
#                     log.warning("Unexpected queue message: %s", raw_message)


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
                os.path.join("clip_library"),
                os.path.join("clip_library", category),
            ]:
                try:
                    os.mkdir(dir)
                except OSError:
                    # the directory already exists.  This is not a problem.
                    pass

        self.start()

    def run(self):
        talking_npc = {}
        pythoncom.CoInitialize()
        raw_message = None
        while True:

            while raw_message is None:
                try:
                    raw_message = self.speaking_queue.get(block=False)
                except queue.Empty:
                    # no new items?  No problem, do our NPC queue bookkeeping.
                    raw_message = None

                    for name in talking_npc:
                        if talking_npc[name]:
                            if hasattr(talking_npc[name][0], "is_playing"):
                                if talking_npc[name][0].is_playing():
                                    # it is still playing, leave it alone.
                                    continue
                                else:
                                    # it is done playing.  Remove it.
                                    talking_npc[name].pop(0)
                        
                        # do we have something else queued up?
                        if talking_npc[name]:
                            talking_npc[name][0] = talking_npc[name][0].play()
                    
                    # so we don't slam the audio subsystem with "is_playing" requests
                    time.sleep(0.2)

            # TODO:  what exactly are the limits on what can safely pass through
            # a queue to a thread?
            try:
                name, message, category = raw_message
            except ValueError:
                log.warning("Unexpected queue message: %s", raw_message)
                continue
            raw_message = None

            if category not in ["npc", "player", "system"]:
                log.error("invalid category: %s", category)
                self.speaking_queue.task_done()
                continue

            phrase_id = models.get_or_create_phrase_id(name, category, message)
            message, is_translated = models.get_translated(phrase_id)

            log.debug(f"Speaking thread received {category} {name}:{message}")

            found = False
            for rank in ['primary', 'secondary']:
                cachefile = settings.get_cachefile(name, message, category, rank)

                # if primary exists, play that.  else secondary.
                if not found and os.path.exists(cachefile):
                    found = True
                    log.debug(f"(tighttts) Cache HIT: {cachefile}")
                    # requires pydub?
                    with AudioFile(cachefile) as input:
                        with AudioFile(
                            filename=cachefile + ".wav",
                            samplerate=input.samplerate,
                            num_channels=input.num_channels,
                        ) as output:
                            while input.tell() < input.frames:
                                output.write(input.read(1024))

                    #
                    #os.unlink(cachefile + ".wav")

                    log.info(f'[{category}] Playing wav file {cachefile}.wav')
                    # if category in ["system",]:
                    #     # sync
                    #     audio = get_audio_from_wav_file(cachefile + ".wav")
                    #     voicebox.sinks.SoundDevice(blocking=False).play(audio)
                    # else:
                    #     # async
                    audio_obj = simpleaudio.WaveObject.from_wave_file(str(cachefile + ".wav"))
                    
                    if category in ["npc", ]:
                        # okay.. with apologies for the level of fancy here. we
                        # don't want characters to be able to talk over
                        # themselves, because that is stupid.
                        talking_npc.setdefault(name, [])
                        talking_npc[name].append(audio_obj)
                    else:
                        play_obj = audio_obj.play()
                        
                        if category in ["system", ]:
                            # sync
                            play_obj.wait_done()                 

            # neither primary nor secondary exist.
            if not found:
                # building session out here instead of inside get_character
                # keeps character alive and properly tied to the database as we
                # pass it into update_character_last_spoke and voice_builder.
                with models.db() as session:
                    character = models.Character.get(name, category, session)

                    models.update_character_last_spoke(character.id, session)

                    # it isn't very well named, but this will speak "message" as
                    # character and cache a copy into cachefile.
                    try:
                        voice_builder.create(character, message, session)
                    except Exception as err:
                        log.exception(err)

            # we've said our piece.
            # self.speaking_queue.task_done()


def plainstring(dialog):
    """
    Clean up any color codes and give us just the basic text string
    """
    dialog = re.sub(r"<scale [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
    dialog = re.sub(r"<bordercolor [#a-zA-Z0-9]+>", "", dialog).strip()
    return dialog

class LogStream:
    """
    This is a streaming processor for the log file.  Its kind of sorely
    deficient in more than one way but seems to be at least barely adequate.
    """
    
    # if we don't get any new lines in this many seconds, double check to make
    # sure we're actually reading the most recent log file.  I think a float
    # would work here too.
    READ_TIMEOUT = 60

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
        speaking_queue: queue,
        event_queue: queue,
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
        
        self.find_character_login()

    def open_latest_log(self):
        all_files = glob.glob(os.path.join(self.logdir, "*.txt"))
        filename = max(all_files, key=os.path.getctime)
        
        log.debug(f'(oll) Setting {self.logfile=}')
        self.logfile = filename
        return open(
            os.path.join(self.logdir, filename),
            encoding="utf-8"
        )

    def find_character_login(self):
        """
        Skim through and see if can find the beginning of the current characters
        login.
        """
        hero_name = None

        # we want the most recent entries of specific strings. This might be
        # better done backwards
        with self.open_latest_log() as handle:
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
            self.hero = Hero(hero_name)
            
            if self.event_queue:
                self.event_queue.put(("SET_CHARACTER", self.hero.name))

            self.speaking_queue.put((None, f"Welcome back {self.hero.name}", "system"))
            if not settings.REPLAY:
                send_log_lock()

        else:
            self.speaking_queue.put((None, "User name not detected", "system"))
            log.warning("Could NOT find hero name.. good luck.")      


    def channel_chat_parser(self, lstring):
        speaker, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
        dialog = plainstring(dialog)
        return speaker, dialog

    def tell_chat_parser(self, lstring):
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
                # player attribute self-reporting
                for keyvalue in dialog.split(';'):
                    try:
                        key, value = keyvalue.split('=')
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

    def channel_messager(self, lstring):
        # channel message
        dialog = " ".join(lstring)
        channel = dialog[1: dialog.find(']')]

        log.info(dialog)
        
        guide = self.channel_guide.get(channel, None)
        if guide and guide['enabled']:
            # channel messages are from someone
            parser = getattr(self, guide['parser'])
            speaker, dialog = parser(lstring)

            # sometimes people don't say anything, like "..." so we drop any
            # non-dialog messages.
            if dialog and dialog.strip():
                if (settings.REPLAY and settings.SPEECH_IN_REPLAY) or not settings.REPLAY:
                    log.info(f"[{channel}] Adding {speaker}/{dialog} to speaking queue")
                    self.speaking_queue.put((speaker, dialog, guide['name']))

        elif guide is None:
            log.debug(f'{channel=}')
        else:
            log.debug(f'{guide=}')

    def tail(self):
        """
        read any new lines that have arrives since we last read the file and
        process each of them.

        We're in a multiprocessing.Process() while True, so the expectation is
        that we aren't going anywhere.

        self.handle needs to be an open, read-able file handle.
        """
        lstring = ""

        with self.open_latest_log() as handle:
            if self.first_tail:
                # New character selected
                log.debug(f'Found new logfile {self.logfile}')
                self.find_character_login()
                models.clear_damage()
            
            if settings.REPLAY:
                # start at the beginning of the log
                log.debug('Seeing to beginning of log file')
                handle.seek(0, 0)
            else:
                # seek to the end of the file in the typical case
                log.debug('Seeing to end of log file')
                handle.seek(0, io.SEEK_END)
            
            # else when replay is true this will process the whole file,
            # essentailly re-playing the session.  This is very handy for
            # diagnostics since it makes your most recent chat log a canned
            # example you can send through the engine over and over.  Super
            # helpful.

            # typical loop
            last_working = time.time()
            log.debug('Entering primary log evaluation loop')
            while settings.REPLAY or (time.time() - last_working < self.READ_TIMEOUT):
                talking = (settings.REPLAY and settings.SPEECH_IN_REPLAY) or not settings.REPLAY

                # read the next line, or return "" if we're at EOF
                line = handle.readline().strip()

                if line:
                    last_working = time.time()
                    try:
                        datestr, timestr, line_string = line.split(None, 2)
                    except ValueError:
                        continue

                    lstring = line_string.replace(".", "").strip().split()
                    # "['Hasten', 'is', 'recharged']"
                    if lstring[0][0] == "[":
                        self.channel_messager(lstring)

                    elif self.announce_badges and lstring[0] == "Congratulations!":
                        self.speaking_queue.put((None, (" ".join(lstring[4:])), "system"))

                    elif lstring[0] == "You":
                        if lstring[1] in ["found", "stole", "begin", "finished"]:
                            # You found a face mask that is covered in some kind of mold. It appears to be pulsing like it's breathing. You send a short video to Watkins for evidence.
                            # You have cleared the Snakes from the Arachnos base, and learned something interesting.
                            # You stole the money!
                            dialog = plainstring(" ".join(lstring))
                            if talking:
                                self.speaking_queue.put((None, dialog, "system"))

                        elif lstring[1] == "have":
                            enabled = False
                            # have is tricky.  lots of things use have.
                            dialog = plainstring(" ".join(lstring))
                            if lstring[2] == "defeated":
                                enabled = settings.get_toggle(settings.taggify("Acknowledge each win"))

                                if talking and enabled:
                                    self.speaking_queue.put((None, dialog, "system"))
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
                                    self.speaking_queue.put((None, dialog, "system"))

                            elif talking:
                                self.speaking_queue.put((None, dialog, "system"))

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
                                self.speaking_queue.put((None, dialog, "system"))

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
                        if lstring[1] == "hit":
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

                    elif lstring[0] == "MISSED":
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
                        # Welcome to City of Heroes, <HERO NAME>
                        self.hero = Hero(" ".join(lstring[5:]).strip("!"))

                        # we want to notify upstream UI about this.
                        self.event_queue.put(("SET_CHARACTER", self.hero.name))

                    elif lstring[-2:] == ["is", "recharged"]:
                        log.debug('Adding RECHARGED event to event_queue...')
                        self.event_queue.put(
                            ("RECHARGED", " ".join(lstring[0:lstring.index("is")]))
                        )

                    elif lstring[-2:] == ["the", "team"]:
                        name = " ".join(lstring[0:-4])
                        action = lstring[-3]  # joined or quit
                        self.speaking_queue.put((None, f"Player {name} has {action} the team", "system"))

                    elif lstring[:2] in ["The", "name", "The", "whiteboard"]:
                        # The name <color red>Toothbreaker Jones</color> keeps popping up, and these Skulls were nice enough to tell you where to find him. Time to pay him a visit.
                        dialog = plainstring(" ".join(lstring))
                        self.speaking_queue.put((None, dialog, "system"))

                    elif lstring[0:2] == ["Your", "combat"]:
                        # 2024-07-26 19:01:05 Your combat improves to level 23! Seek a trainer to further your abilities.
                        level = int(lstring[5].strip('!'))
                        self.speaking_queue.put(
                            (
                                None,
                                f"Congratulations.  You have reached Level {level}",
                                "system",
                            )
                        )

                        # this will update the character tab
                        settings.set_config_key(
                           'level', level, cf='state.json'
                        )

                    # single word things to speak, mostly clicky descriptions
                    elif lstring[0] in ["Something's", "In", "Jones", "This", "You've", "Where"]:
                        # Something's not right with this spot on the floor...
                        # This blotch of petroleum on the ground seems fresh, perhaps leaked by a 'zoombie' and a sign that they're near. You take a photo and send it to Watkins.
                        # You've found a photocopy of a highly detailed page from a medical notebook, with wildly complex notes about cybernetics. 
                        dialog = plainstring(" ".join(lstring))
                        if (settings.REPLAY and settings.SPEECH_IN_REPLAY) or not settings.REPLAY:
                            self.speaking_queue.put((None, dialog, "system"))
                        
                    # else:
                    #    log.warning(f'tag {lstring[0]} not classified.')
                    #
                    # Team task completed.
                    # A new team task has been chosen.
                else:
                    # no need to heat up the house
                    time.sleep(0.125)

            # not exactly a _problem_ but this should be rare.
            log.warning(f'Chat Log READ_TIMEOUT ({self.READ_TIMEOUT}) exceeded.')
            self.first_tail = False

class Hero:
    # keep this update for cheap parlor tricks.
    columns = (
        "id",
        "name",
    )

    def __init__(self, hero_name):
        self.load_hero(hero_name)

    def load_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = session.query(models.Hero).filter_by(name=hero_name).first()

        if hero is None:
            return self.create_hero(hero_name)

        for c in self.columns:
            setattr(self, c, getattr(hero, c))

    def create_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = models.Hero(name=hero_name)
            session.add(hero)
            session.commit()

        # this is a disaster waiting to happen.
        return self.load_hero(hero_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Give NPCs a voice in City of Heroes")
    parser.add_argument(
        "--logdir",
        type=str,
        required=True,
        default="c:\\CoH\\PLAYERNAME\\Logs",
        help="Path to your CoH 'Logs' directory",
    )
    parser.add_argument(
        "--badges",
        type=bool,
        required=False,
        default=True,
        help="When you earn a badge say which badge it is",
    )
    parser.add_argument(
        "--npc",
        type=bool,
        required=False,
        default=True,
        help="when NPCs talk, give them a voice",
    )
    parser.add_argument(
        "--team",
        type=bool,
        required=False,
        default=True,
        help="when your team members talk, give them a voice",
    )

    args = parser.parse_args()

    logdir = args.logdir
    badges = args.badges
    team = args.team
    npc = args.npc

    # create a queue for TTS
    q = queue.Queue()

    # print('Starting TTS Thread')
    # any string we put in this queue will be read out with
    # the default voice.
    TightTTS(q)

    q.put((None, "Ready", "system"))
    time.sleep(0.5)
    q.put((None, "Set", "system"))
    time.sleep(0.5)
    q.put((None, "Go!!", "system"))

    ls = LogStream(logdir, q, badges, npc, team)
    while True:
        ls.tail()


if __name__ == "__main__":
    main()
