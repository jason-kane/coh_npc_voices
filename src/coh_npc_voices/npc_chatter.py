import argparse
import glob
import io
import logging
import os
import queue
import re
import sys
import threading
import time
import io

import db
import pythoncom
import tts.sapi
import voice_builder
import voicebox
from pedalboard.io import AudioFile
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
    def __init__(self, q):
        threading.Thread.__init__(self)
        self.q = q
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
            raw_message = self.q.get()
            try:
                name, message, category = raw_message
            except ValueError:
                log.warning('Unexpected queue message: %s', raw_message)
                continue

            if category not in voice_builder.MESSAGE_CATEGORIES:
                log.error('invalid category: %s', category)
                self.q.task_done()
                continue

            log.info(f'Speaking thread received {category} {name}:{message}')

            name, clean_name = db.clean_customer_name(name)
            log.info(f"{name} -- {clean_name}")

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
                
                # We might have some fancy voices
                cursor = db.get_cursor()
                character_id = cursor.execute(
                    "SELECT id FROM character WHERE name=? AND category=?", 
                    (name, category)
                ).fetchone()
                if character_id:
                    voice_builder.create(character_id[0], message, cachefile)
                else:
                    # this is the first time we've gotten a message from this
                    # NPC, so they don't have a voice yet.  We will default to
                    # the windows voice because it is free and no voice effects.
                    cursor.execute(
                        "INSERT INTO character (name, engine, category) values (?, ?, ?)", 
                        (name, voice_builder.default_engine, category)
                    )
                    db.commit()
                    character_id = cursor.execute(
                        "SELECT id FROM character WHERE name=? and category=?",
                        (name, category)
                    ).fetchone()
                    voice_builder.create(character_id[0], message, cachefile)

            self.q.task_done()


class LogStream:
    def __init__(self, logdir: str, tts_queue: queue, badges: bool, npc: bool, team: bool):
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

        print(f"Tailing {self.filename}...")
        self.handle = open(os.path.join(logdir, self.filename))
        #self.handle.seek(0, io.SEEK_END)
        self.tts_queue = tts_queue

    def tail(self):
        # read any new lines that have arrives since we last read the file and process
        # each of them.
        lstring = ""
        previous = ""
        for line in self.handle.readlines():
            if line.strip():
                # print(line.split(None, 2))
                try:
                    _, _, line_string = line.split(None, 2)
                except ValueError:
                    continue

                previous = lstring
                lstring = line_string.split()
                if self.npc_speak and lstring[0] == "[NPC]":
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    self.tts_queue.put((name, dialog, 'npc'))

                elif self.team_speak and lstring[0] == "[Team]":
                    #['2024-03-30', '23:29:48', '[Team] Khold: <color #010101>ugg, I gotta roll, nice little team.  dangerous without supports\n']
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
                    self.tts_queue.put((name, dialog, 'player'))

                elif self.tell_speak and lstring[0] == "[Tell]":
                    # why is there an extra colon for Tell?  IDK.
                    #2024-04-02 17:56:21 [Tell] :Dressy Bessie: I can bump you up a few levels if you want
                    if lstring[1][:2] == "-->":
                        # this is a reply to a tell, or an outbound tell.
                        dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                        name = None
                    else:
                        try:
                            _, name, dialog = " ".join(lstring[1:]).split(":", maxsplit=2)
                        except ValueError:
                            name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)

                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    self.tts_queue.put((name, dialog, 'player'))

                elif self.caption_speak and lstring[0] == "[Caption]":
                    # 2024-04-02 20:09:50 [Caption] <scalxe 2.75><color red><bgcolor White>My Shadow Simulacrum will destroy Task Force White Sands!
                    name = None
                    dialog = " ".join(lstring[1:])
                    log.debug(f'Adding Caption {dialog} to reading queue')
                    dialog = re.sub(r"<scale [0-9\.]+>", "", dialog).strip()
                    dialog = re.sub(r"<color [#a-zA-Z0-9]+>", "", dialog).strip()
                    dialog = re.sub(r"<bgcolor [#a-zA-Z0-9]+>", "", dialog).strip()
                    self.tts_queue.put((name, dialog, 'player'))

                elif self.announce_badges and lstring[0] == "Congratulations!":
                    self.tts_queue.put(
                        (None, (" ".join(lstring[4:])), 'system')
                    )
                
                elif (
                    self.announce_levels and lstring[0:3] == ["You", "are", "now", "fighting"]
                ) and (
                    " ".join(previous[-4:]) not in [
                        "have quit your team",
                        "has joined the team"
                    ]
                ):
                    # 2024-04-03 20:23:51 You are now fighting at level 4.
                    level = lstring[-1].strip('.')
                    self.tts_queue.put((
                        None, 
                        f"Congratulations.  You've reached Level {level}", 
                        'system'
                    ))

                #else:
                #    log.debug(f'tag {lstring[0]} not classified.')


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
