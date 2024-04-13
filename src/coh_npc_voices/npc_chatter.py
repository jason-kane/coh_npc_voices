import argparse
import glob
import io
import logging
from datetime import datetime
import os
import queue
import re
import sys
import threading
import time

import db
import models
import pythoncom
import tts.sapi
import voice_builder
import voicebox
from pedalboard.io import AudioFile
from sqlalchemy import select, update
from voicebox.tts.utils import get_audio_from_wav_file

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger('__name__')


# TODO:
#   goals: 
#       consistent, unique(-ish) voice for every character in the game that speaks.
#       free option, best possible quality
#       cheap option, multiple options (paying TTS providers, responses cached)
#           how much are we talking?
#
#   Fun:
#       gui voice creator
#       exports to a stringified voice profile
#       players can tell other players what they sound like, and you then hear them.
#       speech-to-text chat input (whisper?)

class TightTTS(threading.Thread):
    def __init__(self, speaking_queue, event_queue):
        threading.Thread.__init__(self)
        self.speaking_queue = speaking_queue
        self.event_queue = event_queue
        self.daemon = True

        # so we can do this much once.
        for category in ['npc', 'player', 'system']:
            for dir in [
                os.path.join("clip_library"),
                os.path.join("clip_library", category)
            ]:
                try:
                    os.mkdir(dir)
                except OSError as error:
                    # the directory already exists.  This is not a problem.
                    pass

        self.start()

    def run(self):
        pythoncom.CoInitialize()
        while True:
            raw_message = self.speaking_queue.get()
            try:
                name, message, category = raw_message
            except ValueError:
                log.warning('Unexpected queue message: %s', raw_message)
                continue

            if category not in ['npc', 'player', 'system']:
                log.error('invalid category: %s', category)
                self.q.task_done()
                continue

            log.info(f'Speaking thread received {category} {name}:{message}')

            name, clean_name = db.clean_customer_name(name)
            log.debug(f"{name} -- {clean_name}")

            #ie: abcde_timetodan.mp3
            filename = db.cache_filename(name, message)
            
            # do we already have this NPC/Message rendered?
            try:
                cachefile = os.path.abspath(
                    os.path.join("clip_library", category, clean_name, filename)
                )
            except Exception:
                log.error(f'invalid os.path.join("clip_library", {category}, {clean_name}, {filename})')
                raise

            try:
                os.mkdir(os.path.join("clip_library", category, clean_name))
            except OSError as error:
                # the directory already exists.  This is not a problem.
                pass

            if os.path.exists(cachefile):
                log.info(f'Cache Hit: {cachefile}')
                # requires pydub
                with AudioFile(cachefile) as input:
                    with AudioFile(
                        filename=cachefile + ".wav",
                        samplerate=input.samplerate, 
                        num_channels=input.num_channels
                    ) as output:

                        while input.tell() < input.frames:
                            output.write(input.read(1024))

                audio = get_audio_from_wav_file(
                    cachefile + ".wav"
                )
                os.unlink(cachefile + ".wav")

                voicebox.sinks.SoundDevice().play(audio)
            else:
                log.info(f'Cache Miss -- {cachefile} not found')
                # ok, what kind of voice do we want for this NPC?
                
                with models.Session(models.engine) as session:
                    character = session.scalars(
                        select(models.Character).where(
                            models.Character.name == name,
                            models.Character.category == models.category_str2int(category)
                        )
                    ).first()

                if character is None:
                    # this is the first time we've gotten a message from this
                    # NPC, so they don't have a voice yet.  We will default to
                    # the windows voice because it is free and no voice effects.
                    with models.Session(models.engine) as session:
                        character = models.Character(
                            name=name,
                            engine=voice_builder.default_engine,
                            category=models.category_str2int(category)
                        )
                        session.add(character)
                        session.commit()
                        session.refresh(character)

                voice_builder.create(character, message, cachefile)

            self.speaking_queue.task_done()


class LogStream:
    def __init__(
            self, 
            logdir: str, 
            speaking_queue: queue, 
            event_queue: queue, 
            badges: bool, npc: bool, team: bool
        ):
        """
        find the most recent logfile in logdir
        note which file it is, open it and skip
        to the end so we're ready to start tailing.
        """
        all_files = glob.glob(os.path.join(logdir, "*.txt"))
        self.filename = max(all_files, key=os.path.getctime)
        self.announce_badges = badges
        self.npc_speak = npc
        self.team_speak = team
        self.tell_speak = True
        self.caption_speak = True
        self.announce_levels = True
        self.hero = None

        print(f"Tailing {self.filename}...")
        self.handle = open(os.path.join(logdir, self.filename))

        self.speaking_queue = speaking_queue
        self.event_queue = event_queue

        # skim through and see if can find the hero name
        for line in self.handle.readlines():
            try:
                datestr, timestr, line_string = line.split(None, 2)
            except ValueError:
                continue
    
            lstring = line_string.split()
            if (lstring[0] == "Welcome"):
                # Welcome to City of Heroes, <HERO NAME>
                self.hero = Hero(" ".join(lstring[5:]).strip('!'))

                # we want to notify upstream UI about this.
                if self.event_queue:
                    self.event_queue.put(
                        ('SET_CHARACTER', self.hero.name)
                    )
        
        if self.hero is None:
            log.info('Could NOT find hero name.. good luck.')

        # now move the file handle to the end, we 
        # will starting parsing everything for real this
        # time.
        self.handle.seek(0, io.SEEK_END)
        #self.handle.seek(0, 0)


    def tail(self):
        # read any new lines that have arrives since we last read the file and process
        # each of them.
        lstring = ""
        previous = ""
        for line in self.handle.readlines():
            if line.strip():
                # print(line.split(None, 2))
                try:
                    datestr, timestr, line_string = line.split(None, 2)
                except ValueError:
                    continue

                previous = lstring
                lstring = line_string.split()
                if self.npc_speak and lstring[0] == "[NPC]":
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bordercolor [#a-zA-Z0-9]+>", "", dialog).strip()

                    self.speaking_queue.put((name, dialog, 'npc'))

                elif self.team_speak and lstring[0] == "[Team]":
                    #['2024-03-30', '23:29:48', '[Team] Khold: <color #010101>ugg, I gotta roll, nice little team.  dangerous without supports\n']
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
                    self.speaking_queue.put((name, dialog, 'player'))

                elif self.tell_speak and lstring[0] == "[Tell]":
                    # why is there an extra colon for Tell?  IDK.
                    #2024-04-02 17:56:21 [Tell] :Dressy Bessie: I can bump you up a few levels if you want
                    if lstring[1][:3] == "-->":
                        # 2024-04-06 20:23:32 [Tell] -->Toxic Timber: pls
                        # this is a reply to a tell, or an outbound tell.
                        dialog = " ".join(lstring[1:]).split(":", maxsplit=1)[-1].strip()
                        name = None
                    else:
                        try:
                            _, name, dialog = " ".join(lstring[1:]).split(":", maxsplit=2)
                        except ValueError:
                            name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)

                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    self.speaking_queue.put((name, dialog, 'player'))

                elif self.caption_speak and lstring[0] == "[Caption]":
                    # 2024-04-02 20:09:50 [Caption] <scalxe 2.75><color red><bgcolor White>My Shadow Simulacrum will destroy Task Force White Sands!
                    name = None
                    dialog = " ".join(lstring[1:])
                    log.debug(f'Adding Caption {dialog} to reading queue')
                    dialog = re.sub(r"<scale [0-9\.]+>", "", dialog).strip()
                    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
                    self.speaking_queue.put((name, dialog, 'player'))

                elif self.announce_badges and lstring[0] == "Congratulations!":
                    self.speaking_queue.put(
                        (None, (" ".join(lstring[4:])), 'system')
                    )
                
                elif (lstring[0] == "You"):
                    if lstring[1] == "are":
                        if (self.announce_levels and lstring[2:3] == ["now", "fighting"]) and (
                        " ".join(previous[-4:]) not in [
                            "have quit your team",
                            "has joined the team"
                        ]):
                            level = lstring[-1].strip('.')
                            self.speaking_queue.put((
                                None, 
                                f"Congratulations.  You've reached Level {level}", 
                                'system'
                            ))
                
                    elif self.hero and lstring[1] == "gain":
                        # 2024-04-05 21:43:45 You gain 104 experience and 36 influence.
                        # I'm just going to make the database carry the burden, so much easier.
                        # is this string stable enough to get away with this?  It's friggin'
                        # cheating.
                        
                        # You gain 250 influence.
                        try:
                            influence_index = lstring.index("influence.") - 1
                            inf_gain = int(lstring[influence_index])
                        except ValueError:
                            inf_gain = None                       

                        try:
                            xp_index = lstring.index('experience') - 1
                            xp_gain = int(lstring[xp_index])
                        except ValueError:
                            xp_gain = None                            

                        try:
                            did_i_defeat_it = previous.index('defeated')
                            foe = " ".join(previous[did_i_defeat_it:])
                        except ValueError:
                            # no, someone else did.  you just got some 
                            # points for it.  Lazybones.
                            foe = None                       

                        with models.Session(models.engine) as session:
                            new_event = models.HeroStatEvent(
                                hero_id=self.hero.id,
                                event_time=datetime.strptime(
                                    f"{datestr} {timestr}",
                                    "%Y-%m-%d %H:%M:%S"
                                ),
                                xp_gain=xp_gain,
                                inf_gain=inf_gain
                            )
                            session.add(new_event)
                            session.commit()

                elif (lstring[0] == "Welcome"):
                    # Welcome to City of Heroes, <HERO NAME>
                    self.hero = Hero(" ".join(lstring[5:]).strip('!'))

                    # we want to notify upstream UI about this.
                    self.event_queue.put(
                        ('SET_CHARACTER', self.hero.name)
                    )                    
                    
                #else:
                #    log.warning(f'tag {lstring[0]} not classified.')

class Hero:
    # keep this update for cheap parlor tricks.
    columns = ("id", "name", )

    def __init__(self, hero_name):
        self.load_hero(hero_name)

    def load_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = session.query(
                models.Hero
            ).filter_by(
                name=hero_name
            ).first()

        if hero is None:
            return self.create_hero(hero_name)
        
        for c in self.columns:
            setattr(self, c, getattr(hero, c))

    def create_hero(self, hero_name):
        with models.Session(models.engine) as session:
            hero = models.Hero(
                name = hero_name
            )
            session.add(hero)
            session.commit()

        # this is a disaster waiting to happen.
        return self.load_hero(hero_name)


def main() -> None:
    parser = argparse.ArgumentParser(description='Give NPCs a voice in City of Heroes')
    parser.add_argument("--logdir", type=str, required=True, default="c:\\CoH\\PLAYERNAME\\Logs", help="Path to your CoH 'Logs' directory")
    parser.add_argument('--badges', type=bool, required=False, default=True, help="When you earn a badge say which badge it is")
    parser.add_argument('--npc', type=bool, required=False, default=True, help="when NPCs talk, give them a voice")
    parser.add_argument('--team', type=bool, required=False, default=True, help="when your team members talk, give them a voice")

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

    q.put((None, "Ready", 'system'))
    time.sleep(0.5)
    q.put((None, "Set", 'system'))
    time.sleep(0.5)
    q.put((None, "Go!!", 'system'))

    ls = LogStream(logdir, q, badges, npc, team)
    while True:
        ls.tail()

if __name__ == "__main__":
    main()
