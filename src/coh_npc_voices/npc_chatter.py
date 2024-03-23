import glob
import io
import os
import queue
import threading
import time
import argparse

import pythoncom

import tts.sapi

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
            message = self.q.get()
            voice.set_rate(2)
            voice.say(message)
            self.q.task_done()


class LogStream:
    def __init__(self, logdir: str, tts_queue: queue, badges: bool, npc: bool):
        """
        find the most recent logfile in logdir
        note which file it is, open it and skip
        to the end so we're ready to start tailing.
        """
        all_files = glob.glob(os.path.join(logdir, "*.txt"))
        self.filename = max(all_files, key=os.path.getctime)
        self.announce_badges = badges
        self.npc_speak = npc

        print(f"Tailing {self.filename}...")
        self.handle = open(os.path.join(logdir, self.filename))
        self.handle.seek(0, io.SEEK_END)
        self.tts_queue = tts_queue

    def tail(self):
        # read any new lines that have arrives since we last read the file and process
        # each of them.
        for line in self.handle.readlines():
            if line:
                print(line.split(None, 2))
                _, _, line_string = line.split(None, 2)

                lstring = line_string.split()
                if self.npc_speak and lstring[0] == "[NPC]":
                    name, dialog = line_string.split(":", maxsplit=1)
                    self.tts_queue.put(dialog)

                elif self.announce_badges and lstring[0] == "Congratulations!":
                    self.tts_queue.put(" ".join(lstring[4:]))


def main() -> None:
    parser = argparse.ArgumentParser(description='Give NPCs a voice in City of Heroes')
    parser.add_argument("--logdir", type=str, required=True, default="c:\CoH\PLAYERNAME\Logs", help="Path to your CoH 'Logs' directory")
    parser.add_argument('--badges', type=bool, required=False, default=True, help="When you earn a badge say which badge it is")
    parser.add_argument('--npc', type=bool, required=False, default=True, help="when NPCs talk, give them a voice")

    args = parser.parse_args()
    
    logdir = args.logdir
    badges = args.badges
    npc = args.npc

    # create a queue for TTS
    q = queue.Queue()

    # print('Starting TTS Thread')
    # any string we put in this queue will be read out with
    # the default voice.
    TTS(q)

    q.put("Ready")
    time.sleep(0.5)
    q.put("Set")
    time.sleep(0.5)
    q.put("Go!!")

    ls = LogStream(logdir, q, badges, npc)
    while True:
        ls.tail()

if __name__ == "__main__":
    main()
