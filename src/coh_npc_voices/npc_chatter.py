import argparse
import glob
import hashlib
import io
import logging
import os
import queue
import voicebox
import re
import sqlite3
import string
import sys
import threading
import time
import pydub
import pythoncom
import tts.sapi
import voice_builder

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger('__name__')


# TODO:
#  Try https://voicebox.readthedocs.io/en/stable/
#   does this even work in windows?
#
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


class TTS(threading.Thread):
    def __init__(self, q):
        threading.Thread.__init__(self)
        self.q = q
        self.daemon = True
        self.start()

    def run(self):
        pythoncom.CoInitialize()
        voice = tts.sapi.Sapi()
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

            log.debug(f'Speaking thread received {category} {name}:{message}')

            if name:
                clean_name = re.sub(r'[^\w]', '', name)
            else:
                name = "GREAT_NAMELESS_ONE"
                clean_name = "GREAT_NAMELESS_ONE"

            clean_message = re.sub(r'[^\w]', '', message)
            
            #ie: abcde_timetodan.mp3
            filename = hashlib.sha256(name.encode()).hexdigest()[:5] + f"_{clean_message[:10]}"
            
            # do we already have this NPC/Message rendered?
            cachefile = os.path.abspath(os.path.join("clip_library", category, clean_name, f"{filename}.mp3"))

            for dir in [
                os.path.join("clip_library"),
                os.path.join("clip_library", category),
                os.path.join("clip_library", category, clean_name)
            ]:
                try:
                    os.mkdir(dir)
                except OSError as error:
                    # the directory already exists.  This is not a problem.
                    pass

            if os.path.exists(cachefile):
                log.info(f'Cache Hit: {cachefile}')
                # we already have this one.  Use it.
                # cachefile = cachefile.replace(r"\\", "\\\\") 
                # mp3play.load(cachefile).play()
                audio = voicebox.tts.utils.get_audio_from_mp3(cachefile)
                voicebox.sinks.SoundDevice().play(audio)
            else:
                log.info(f'Cache Miss -- {cachefile} not found')
                # ok, what kind of voice do we want for this NPC?
                if os.path.exists('voices.db'):
                    # We might have some fancy voices
                    con = sqlite3.connect("voices.db")
                    cursor = con.cursor()
                    character_id = cursor.execute(
                        "SELECT id FROM character WHERE name=? AND category=?", 
                        (name, category)
                    ).fetchone()
                    if character_id:
                        voice_builder.create(con, character_id[0], message, cachefile)
                    else:
                        # this is the first time we've gotten a message from this
                        # NPC, so they don't have a voice yet.  We will default to
                        # the windows voice because it is free and no voice effects.
                        cursor.execute(
                            "INSERT INTO character (name, engine, category) values (?, ?, ?)", 
                            (name, voice_builder.default_engine, category)
                        )
                        con.commit()
                        character_id = cursor.execute(
                            "SELECT id FROM character WHERE name=? and category=?",
                            (name, category)
                        ).fetchone()
                        voice_builder.create(con, character_id[0], message, cachefile)
                else:
                    # we aren't using the sqlite backed persistence, just make an on-the-fly message
                    # and we are done.
                    voice.set_rate(2)
                    voice.say(message) # quick response for the user experience
                    # then generate an mp3 to store and play for next time
                    # strange for local voices?  but not for paid text to voice.
                    # a fraction of a cent _once_ for each bit of dialog in game 
                    # is cheap.  A fraction every time anyone says anything, that
                    # adds up, so the cache makes it cheap.
                    #
                    # mp3 because it's so universal.  There are a million and 10
                    # existing tools for manipulating mp3.
                    log.info(f'Creating {cachefile}.wav')
                    voice.create_recording(cachefile + ".wav", message)
                    audio = pydub.AudioSegment.from_wav(cachefile + ".wav")
                    audio.export(cachefile, format="mp3")
                    os.unlink(cachefile + ".wav")

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

        print(f"Tailing {self.filename}...")
        self.handle = open(os.path.join(logdir, self.filename))
        # self.handle.seek(0, io.SEEK_END)
        self.tts_queue = tts_queue

    def tail(self):
        # read any new lines that have arrives since we last read the file and process
        # each of them.
        for line in self.handle.readlines():
            if line.strip():
                print(line.split(None, 2))
                try:
                    _, _, line_string = line.split(None, 2)
                except ValueError:
                    continue

                lstring = line_string.split()
                if self.npc_speak and lstring[0] == "[NPC]":
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    self.tts_queue.put((name, dialog, 'npc'))

                elif self.team_speak and lstring[0] == "[Team]":
                    name, dialog = " ".join(lstring[1:]).split(":", maxsplit=1)
                    log.debug(f'Adding {name}/{dialog} to reading queue')
                    name = re.sub(r"<color #[a-f0-9]+>", "", name).strip()
                    name = re.sub(r"<bgcolor #[a-f0-9]+>", "", name).strip()
                    self.tts_queue.put((name, dialog, 'player'))

                elif self.announce_badges and lstring[0] == "Congratulations!":
                    self.tts_queue.put(
                        (None, (" ".join(lstring[4:])), 'system')
                    )
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
    TTS(q)

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
