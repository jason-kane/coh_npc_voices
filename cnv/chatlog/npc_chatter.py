import glob
import hashlib
import io
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime

import lib.settings as settings
import pygame
import pythoncom
from pedalboard.io import AudioFile

import cnv.database.models as models
import cnv.logger
import cnv.voices.voice_builder as voice_builder
from cnv.lib.proc import send_log_lock

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
            log.info('[TightTTS] Top of True')
            while self.speaking_queue.empty():
                time.sleep(0.25)

            log.info('Retrieving queued message')
            raw_message = self.speaking_queue.get()

            log.info('[TightTTS] TTS Message received: %s', raw_message)
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

            log.debug(f"[TightTTS] Speaking thread received {category} {name}:{message}")

            found = False
            for rank in ['primary', 'secondary']:
                cachefile = settings.get_cachefile(name, message, category, rank)

                # if primary exists, play that.  else secondary.
                if not found and os.path.exists(cachefile):
                    found = True
                    log.debug(f"[TightTTS] (tighttts) Cache HIT: {cachefile}")
                    # requires pydub?
                    with AudioFile(cachefile) as input:
                        with AudioFile(
                            filename=cachefile + ".wav",
                            samplerate=input.samplerate,
                            num_channels=input.num_channels,
                        ) as output:
                            while input.tell() < input.frames:
                                output.write(input.read(1024))

                    
                    fn = str(cachefile + ".wav")

                    if category in ["npc", "player"]:
                        # okay.. with apologies for the level of fancy here. we
                        # don't want characters to be able to talk over
                        # themselves, because that is stupid.
                        
                        # But.. we've got 8 channels.  We can't give _every_
                        # character a channel. each channel can queue, so.. lets
                        # try the cheap way.  I misunderstood the depth of the
                        # queue (only one item)

                        # lets consistent hash our npc names into channels
                        channel_index = int(hashlib.sha256(name.encode()).hexdigest()[:3], 16) % (len(self.channels) - 1)

                        channel = self.channels[1 + channel_index]
                        
                        log.info(f'[TightTTS] [{category}][{1 + channel_index}] Playing wav file {fn}')
                        if channel.get_queue():
                            # drain the queue until a spot is available
                            while channel.get_queue():
                                log.info(f'Waiting for channel {1+channel_index} queue availability...')
                                pygame.time.wait(250)  # milliseconds
                        
                        channel.queue(
                            pygame.mixer.Sound(file=fn)
                        )

                    else:                        
                        if category in ["system", ]:
                            # when the system is talking, no one interrupts.
                           
                            # the zero channel is for system messages
                            channel = self.channels[0]

                            log.info(f'[TightTTS] [{category}][0] Playing wav file {fn}')
                            # wait for the queue spot to be available
                            
                            while channel.get_queue():
                                log.info('Waiting for system channel queue availability...')
                                pygame.time.wait(250)  # milliseconds
                            
                            channel.queue(
                                pygame.mixer.Sound(file=fn)
                            )

                            log.info('[TightTTS] audio completed')
                        else:
                            log.error('Unknown category: %s', category)

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
        # channel message
        dialog = line_string.strip()
        if ']' in dialog:
            channel = dialog[1: dialog.find(']')]
        else:
            log.error('Malformed channel message: %s', line_string)
            return

        log.info("dialog: %s", dialog)
        
        guide = self.channel_guide.get(channel, None)
        if guide and guide['enabled']:
            log.info('Applying channel guide %s', guide)
            # channel messages are _from_ someone, the parsers extract that.
            parser = getattr(self, guide['parser'])
            speaker, dialog = parser(lstring)

            # sometimes people don't say anything we can vocalize, like "..." so we drop any
            # non-dialog messages.
            if speaker not in ['__self__'] and dialog and dialog.strip():
                log.info(f"[{channel}] Adding {speaker}/{dialog} to speaking queue")
                # speaker name, spoken dialog, channel (npc, system, player)
                self.speaking_queue.put((speaker, dialog, guide['name']))

        elif guide is None:
            log.debug(f'{channel=}')
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
                    log.info('primary log evaluation loop')
                    activity_count = 0
                else:
                    activity_count += 1

                for line in handle:
                    log.debug("line: '%s'", line)

                    if line.strip():
                        log.debug('Top of True')               
                        talking = True
                        
                        try:
                            datestr, timestr, line_string = line.split(None, 2)
                        except ValueError:
                            log.error('Invalid line.split(%s)', line)
                            continue

                        log.info('line_string: %s', line_string)
                        try:
                            lstring = line_string.replace(".", "").strip().split()
                            # "['Hasten', 'is', 'recharged']" 
                            log.info("lstring: %s", lstring)
                        except Exception as err:
                            log.error(err)
                            raise

                        if lstring[0][0] == "[":
                            log.info('Invoking channel_messager()')
                            self.channel_messager(lstring, line_string)
                            log.info('Returned from channel_messager()')
                            continue

                        elif self.announce_badges and lstring[0] == "Congratulations!":
                            self.ssay(" ".join(lstring[4:]))

                        elif lstring[0] == "You":
                            log.info('"You" path')
                            if lstring[1] in ["found", "stole", "begin", "finished", "open", "didn't", "rescued"]:
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


                        elif lstring[-2:] == ["is", "recharged"]:
                            log.debug('Adding RECHARGED event to event_queue...')
                            self.event_queue.put(
                                ("RECHARGED", " ".join(lstring[0:lstring.index("is")]))
                            )

                        elif lstring[-2:] == ["the", "team"]:
                            name = " ".join(lstring[0:-4])
                            action = lstring[-3]  # joined or quit
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

                        # single word things to speak, mostly clicky descriptions
                        elif lstring[0] in ["Something's", "In", "Jones", "This", "You've", "Where"]:
                            # Something's not right with this spot on the floor...
                            # This blotch of petroleum on the ground seems fresh, perhaps leaked by a 'zoombie' and a sign that they're near. You take a photo and send it to Watkins.
                            # You've found a photocopy of a highly detailed page from a medical notebook, with wildly complex notes about cybernetics. 
                            dialog = plainstring(" ".join(lstring))
                            if (settings.REPLAY and settings.SPEECH_IN_REPLAY) or not settings.REPLAY:
                                self.ssay(dialog)
                            
                        else:
                            log.warning(f'tag "{lstring[0]}" not classified.')
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
