"""
There is more awesome to be had.
"""
import ctypes
import logging
import multiprocessing
import queue
import sys
from datetime import datetime, timedelta

import cnv.logger
from cnv.database import models
import colorama
import customtkinter as ctk
import lib.settings as settings
import pyautogui as p
import win32api
import win32con
import win32process
from tabs import (
    automation,
    character,
    configuration,
    voices,
)
from win32gui import GetForegroundWindow, GetWindowText

# this unlinks us from python so windows will
# use our icon instead of the python icon in the
# taskbar.
myappid = u'fun.side.projects.sidekick.1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

cnv.logger.init()
log = logging.getLogger(__name__)
EXIT = False

class MainTabView(ctk.CTkTabview):
    def __init__(self, master, event_queue, speaking_queue, **kwargs):
        kwargs["height"] = 1024  # this is really more like maxheight
        #kwargs['border_color'] = "darkgrey"
        #kwargs['border_width'] = 2
        kwargs['anchor'] = 'nw'
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tabdict = {}

        for tablabel, tabobj, args in (
            ('Character', character.CharacterTab, (event_queue, speaking_queue)),
            ('Voices', voices.VoicesTab, (event_queue, speaking_queue)), 
            ('Configuration', configuration.ConfigurationTab, (event_queue, speaking_queue)),
            ('Automation', automation.AutomationTab, (event_queue, speaking_queue)),
        ):
            ctkframe = self.add(tablabel)
            ctkframe.grid_columnconfigure(0, weight=1)
            ctkframe.grid_rowconfigure(0, weight=1)
            
            self.tabdict[tablabel] = tabobj(ctkframe, *args)
            self.tabdict[tablabel].grid(column=0, row=0, sticky='nsew')


def main():
    colorama.init()
    #root = tk.Tk()  
    root = ctk.CTk()

    def on_closing():
        global EXIT
        EXIT = True
        log.info('Exiting...')
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.iconbitmap("sidekick.ico")

    root.geometry("720x640+200+200")
    root.resizable(True, True)
    root.title("City of Heroes Sidekick")

    event_queue = multiprocessing.Queue()
    speaking_queue = multiprocessing.Queue()
    #queue.Queue()

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)
    
    buffer = ctk.CTkFrame(root)
    buffer.grid_columnconfigure(0, weight=1)
    buffer.grid_rowconfigure(0, weight=1)

    mtv = MainTabView(
        buffer, 
        event_queue=event_queue,
        speaking_queue=speaking_queue
    )
    mtv.grid(
        column=0, row=0, sticky="new"
    )
    buffer.grid(column=0, row=0, sticky="nsew")
    
    # in the mainloop we want to know if event_queue gets a new
    # entry.
    last_character_update = None
    
    # update the graph(s) this often
    update_frequency = timedelta(minutes=1)

    while not EXIT:
        # our primary event loop
        try:
            # the event queue is how messages are sent up
            # from children.
            try:
                event_action = event_queue.get(block=False)
            except queue.Empty:
                event_action = None, None

            # we got an action (no exception)
            # log.info('Event Received: %s', event_action)
            key, value = event_action
            
            if key == "SET_CHARACTER":
                # if this chatter hasn't been started this 
                # will fail.
                # speaking_queue.put(
                #     (None, f"Welcome back {value}", "system")
                # )
                models.set_hero(name=value)
                mtv.tabdict['Character'].set_hero()

                #log.debug('path set_chraracter')
                #char.chatter.hero = npc_chatter.Hero(value)
                #log.debug('Calling set_hero()...')
                #char.set_hero()
                last_character_update = datetime.now()
            elif key == "SPOKE":
                # name, category = value
                log.debug('Refreshing character list...')
                mtv.tabdict['Voices'].listside.refresh_character_list()
            elif key == "RECHARGED":
                log.debug(f'Power {value} has recharged.')
                if value in ["Hasten", "Domination"]:
                    if settings.get_config_key(f'auto_{value.lower()}'):
                        # only send keyboard activity to the city of heroes window
                        # if it is not the foreground window do not do anything.
                        foreground_window_handle = GetForegroundWindow()
                        pid = win32process.GetWindowThreadProcessId(foreground_window_handle)
                        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid[1])
                        
                        proc_name = win32process.GetModuleFileNameEx(handle, 0)
                        zone = GetWindowText(foreground_window_handle)
                        log.info(f'{zone=}')

                        if proc_name.split("\\")[-1] == "cityofheroes.exe":
                            log.info(f'Triggering {value}')
                            p.press("enter")
                            p.typewrite(f"/powexec_name \"{value}\"\n")
                        else:
                            log.info(f'Not touch the keyboard of {proc_name!r}.  That would be rude.')
                    else:
                        log.info(f'auto_{value.lower()} is disabled')

            # else:
            #     log.error('Unknown event_queue key: %s', key)

        except Exception as err:
            log.error(f"{err=}")
            raise
        
        if last_character_update:
            elapsed = datetime.now() - last_character_update
            if elapsed > update_frequency:
                mtv.tabdict['Character'].set_hero()
                last_character_update = datetime.now()

        root.update_idletasks()
        root.update()

if __name__ == '__main__':

    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    main()