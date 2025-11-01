
import logging
import multiprocessing
import tkinter as tk
from datetime import datetime, timedelta
import time
import cnv.database.models as models
import customtkinter as ctk
import matplotlib.dates as mdates
# import numpy as np
from cnv.chatlog import npc_chatter
from cnv.lib import settings
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from sqlalchemy import func, select

from logging.handlers import QueueHandler, QueueListener

log = logging.getLogger(__name__)


class ChatterService:
    def start(self, event_queue, speaking_queue):
        log.info('ChatterService.start()')
        
        npc_chatter.TightTTS(speaking_queue, event_queue)
        speaking_queue.put((None, "Attaching to most recent log...", 'system'))

        logdir = settings.log_dir()

        ls = npc_chatter.LogStream(
            logdir, speaking_queue, event_queue
        )
        
        # while True:
        log.info('invoking LogStream.tail()')
        try:
            ls.tail()
        except Exception as err:
            log.error(err)
            raise

        log.error('tail() exited')


class Chatter(ctk.CTkFrame):
    attach_label = 'Attach to Log'
    detach_label = "Detach from Log"

    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.event_queue = event_queue
        self.speaking_queue = speaking_queue
        self.button_text = tk.StringVar(value=self.attach_label)
        self.attached = False
        self.hero = None
        
        # expand the entry box
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)

        ctk.CTkButton(
            self, 
            textvariable=self.button_text, 
            command=self.attach_chatter
        ).grid(column=0, row=0)

        self.chatter_service = ChatterService()

    def attach_chatter(self):
        """
        Not sure exactly how I want to do this.  I think the best long term
        option is to just launch a process and be done with it.
        """

        if self.attached:
            # we are already attached, I guess we want to stop.
            log.info('Terminating Chatter')
            self.p.terminate()
            self.button_text.set(self.attach_label)
            self.attached = False
            log.debug('Detached')
        else:
            # we are not attached, lets do that.
            log.info('Constructing chatter_service process')
            self.button_text.set(self.detach_label)
            self.p = multiprocessing.Process(
                target=self.chatter_service.start, 
                args=(
                    self.event_queue,
                    self.speaking_queue,
                )
            )
            self.p.start()
            self.attached = True
            log.debug('Attached')


class LogTab(ctk.CTkFrame):
    def __init__(self, parent, event_queue, speaking_queue, log_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.event_queue = event_queue
        self.speaking_queue = speaking_queue
        self.log_queue = log_queue

        # root.columnconfigure(0, weight=1)
        # root.rowconfigure(0, weight=1)
        # Create the panes and frames
        vertical_pane = ttk.PanedWindow(self, orient=VERTICAL)
        vertical_pane.grid(row=0, column=0, sticky="nsew")
        horizontal_pane = ttk.PanedWindow(vertical_pane, orient=HORIZONTAL)
        vertical_pane.add(horizontal_pane)
        
        console_frame = ttk.Labelframe(horizontal_pane, text="Streaming log")
        console_frame.columnconfigure(0, weight=1)
        console_frame.rowconfigure(0, weight=1)
        horizontal_pane.add(console_frame, weight=1)

        self.console = ConsoleUi(console_frame, log_queue)


##
## https://raw.githubusercontent.com/beenje/tkinter-logging-text-widget/refs/heads/master/main.py
##
import datetime
import queue
import logging
import signal
import time
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk, VERTICAL, HORIZONTAL, N, S, E, W
from rich.logging import RichHandler


# class QueueHandler(RichHandler):
#     """Class to send logging records to a queue

#     It can be used from different threads
#     The ConsoleUi class polls this queue to display records in a ScrolledText widget
#     """
#     # Example from Moshe Kaplan: https://gist.github.com/moshekaplan/c425f861de7bbf28ef06
#     # (https://stackoverflow.com/questions/13318742/python-logging-to-tkinter-text-widget) is not thread safe!
#     # See https://stackoverflow.com/questions/43909849/tkinter-python-crashes-on-new-thread-trying-to-log-on-main-thread

#     def __init__(self, log_queue, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.log_queue = log_queue

#     def emit(self, record):
#         print('Emitting log record %s to log_queue %s', record, self.log_queue)
#         self.log_queue.put(record)


class ConsoleUi:
    """Poll messages from a logging queue and display them in a scrolled text widget"""

    def __init__(self, frame, log_queue):
        self.frame = frame
        # Create a ScrolledText wdiget
        self.scrolled_text = ScrolledText(frame, state='disabled', height=12)
        self.scrolled_text.grid(row=0, column=0, sticky=(N, S, W, E))
        self.scrolled_text.configure(font='TkFixedFont')
        self.scrolled_text.tag_config('INFO', foreground='black')
        self.scrolled_text.tag_config('DEBUG', foreground='gray')
        self.scrolled_text.tag_config('WARNING', foreground='orange')
        self.scrolled_text.tag_config('ERROR', foreground='red')
        self.scrolled_text.tag_config('CRITICAL', foreground='red', underline=1)
        # Create a logging handler using a queue
        
        #self.queue_handler = QueueHandler(log_queue)
        # formatter = logging.Formatter('%(asctime)s: %(message)s')
        # self.queue_handler.setFormatter(formatter)
        #log.addHandler(self.queue_handler)
        # Start polling messages from the queue
        listener = QueueListener(
            log_queue,
            self.display
        )
        listener.start()   

        #self.frame.after(100, self.poll_log_queue, log_queue)

    def display(self, *args, **kwargs):
        print(args)
        print(kwargs)
        # msg = self.queue_handler.format(record)
        msg = record
        self.scrolled_text.configure(state='normal')
        self.scrolled_text.insert(tk.END, msg + '\n', record.levelname)
        self.scrolled_text.configure(state='disabled')
        # Autoscroll to the bottom
        self.scrolled_text.yview(tk.END)

    # def poll_log_queue(self, log_queue):
    #     while True:
    #         try:
    #             record = log_queue.get(block=False)
    #         except queue.Empty:
    #             break
    #         else:
    #             print("New log record:", record)
    #             self.display(record)
    #     self.frame.after(100, self.poll_log_queue, log_queue)



