"""
There is more awesome to be had.
"""
import sys, os
sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(
                os.path.realpath(__file__)
            ), 
        '..', '..')
    )
)

import ctypes
import logging
import win32process
import win32con
import win32api

import multiprocessing
import tkinter as tk
from datetime import datetime, timedelta
from logging.config import dictConfig
from tkinter import ttk

from src.coh_npc_voices import engines
import matplotlib.dates as md
import matplotlib.dates as mdates
import models
import npc_chatter
import numpy as np
import pyautogui as p
from win32gui import GetWindowText, GetForegroundWindow
import settings
import voice_editor
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from sqlalchemy import func, select

# this unlinks us from python so windows will
# use our icon instead of the python icon in the
# taskbar.
myappid = u'fun.side.projects.sidekick.1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

LOGGING_CONFIG = { 
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': { 
        'standard': { 
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': { 
        'default': { 
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler'
        },
        'error_file': { 
            'level': 'ERROR',
            'formatter': 'standard',
            'class': 'logging.FileHandler',
            'filename': 'error.log',
            'mode': 'a'
        },
    },
    'loggers': { 
        '': {  # root logger
            'handlers': ['default', 'error_file'],
            'level': 'DEBUG',
            'propagate': True
        },
        # 'coh_npc_voices': {
        #     'handlers': ['default', 'error_file'],
        #     'level': 'DEBUG',
        #     'propagate': True
        # },
    } 
}

dictConfig(LOGGING_CONFIG)
# # log info to stdout
# logging.basicConfig(
#     level=settings.LOGLEVEL,
#     format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
#     handlers=[logging.StreamHandler(sys.stdout)],
# )
# logging.basicConfig(
#     filename="sidekick.log",
#     level=logging.ERROR,
#     format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
# )

log = logging.getLogger(__name__)

class ChartFrame(ttk.Frame):
    def __init__(self, parent, hero, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        log.debug('Initializing ChartFrame()')
        if not hero:
            return
        else:
            log.debug(f'Drawing graph for {hero}')
            self.hero = hero
            # draw graph for $category progress, total per/minute
            # binned to the minute for the last hour.

            # the figure that will contain the plot 
            fig = Figure(
                figsize = (5, 2), 
                dpi = 100
            ) 
               
            # adding the subplot 
            ax = fig.add_subplot(111) 
            ax.tick_params(axis='x', rotation=60)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H-%M'))
        
            self.category = "xp"
            log.debug(f'Retrieving {self.category} data')
            try:
                with models.Session(models.engine) as session:
                    latest_event = session.scalars(
                        select(models.HeroStatEvent).where(
                            models.HeroStatEvent.hero_id == self.hero.id
                        ).order_by(
                            models.HeroStatEvent.event_time.desc()
                        )
                    ).first()
            except Exception as err:
                log.error('Unable to determine latest event')
                log.error(err)
                raise
            
            log.debug(f'latest_event: {latest_event}')

            if latest_event:
                end_time = latest_event.event_time
            else:
                log.info(f'No previous events found for {self.hero.name}')
                end_time = datetime.now()

            start_time = end_time - timedelta(minutes=120)
            log.debug(f'Graphing {self.category} gain between {start_time} and {end_time}')

            with models.db() as session:
                log.debug('Gathering samples')
                try:
                    raw_samples = session.scalars(
                        select(
                            models.HeroStatEvent
                        ).where(
                            models.HeroStatEvent.hero_id == self.hero.id,
                            models.HeroStatEvent.event_time >= start_time,
                            models.HeroStatEvent.event_time <= end_time,
                        )
                    ).all()
                except Exception as err:
                    log.error('Error gathering data samples')
                    log.error(err)
                    raise


                # do some binning in per-minute buckets in the database.
                log.debug('Gathering binned samples')
                try:
                    samples = session.execute(
                        select(
                            func.STRFTIME('%Y-%m-%d %H:%M:00', models.HeroStatEvent.event_time).label('EventMinute'),
                            func.sum(models.HeroStatEvent.xp_gain).label('xp_gain'),
                            func.sum(models.HeroStatEvent.inf_gain).label('inf_gain')
                        ).where(
                            models.HeroStatEvent.hero_id == self.hero.id,
                            models.HeroStatEvent.event_time >= start_time,
                            models.HeroStatEvent.event_time <= end_time,
                        ).group_by(
                            'EventMinute'
                            # func.STRFTIME('%Y-%m-%d %H:%M:00', models.HeroStatEvent.event_time)
                        ).order_by(
                            'EventMinute'
                        )
                    ).all()
                except Exception as err:
                    log.error('Error gathering data samples')
                    log.error(err)
                    raise
            
            log.debug(f'Found {len(samples)} binned samples, {len(raw_samples)} raw values')

            data_timestamp = []
            data_xp = []
            data_inf = []
            rolling_data_xp = []
            rolling_xp_list = []
            roll_size = 5
            previous_event = None
            sum_xp = 0
            sum_inf = 0

            for row in samples:
                # per bin
                log.debug(f'row: {row}')
                datestring, xp_gain, inf_gain = row

                if xp_gain:
                    sum_xp += xp_gain
                if inf_gain:
                    sum_inf += inf_gain
                event_time = datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S") 
                
                while previous_event and (event_time - previous_event) > timedelta(minutes=1, seconds=30):
                    log.debug('Adding a zero value to fill in a gap')
                    # We have a time gap; fill it with zeroes to keep our calculations truthy
                    new_event_time = previous_event + timedelta(minutes=1)
                    data_timestamp.append(new_event_time)
                    data_xp.append(0)
                    data_inf.append(0)
                    rolling_xp_list.append(0)
                    
                    rolling_data_xp.append(np.mean(rolling_xp_list[-1 * roll_size:]))

                    previous_event = new_event_time
                               
                data_timestamp.append(event_time)

                data_xp.append(xp_gain)
                data_inf.append(inf_gain)
                rolling_xp_list.append(xp_gain)

                log.debug(f'{rolling_xp_list=}')
                if any(rolling_xp_list):
                    rolling_average_value = np.mean(rolling_xp_list[-1 * roll_size:])
                else:
                    rolling_average_value = 0

                log.debug(f'{rolling_average_value=}')
                rolling_data_xp.append(rolling_average_value)
                log.debug(f'{rolling_data_xp=}')

                # log.info(f'{data_xp=}')
                # log.info(f'{data_inf=}')
                # log.info(f'{rolling_xp_list=}')
                # log.info(f'{rolling_data_xp=}')
                # log.info(f'{rolling_average_value=}')

                #try:
                
                # except Exception as err:
                #     log.error(err)
                #     log.error(f'rolling_xp_list: {rolling_xp_list[-1 * roll_size:]}')
                #     raise

                # while len(rolling_xp_list) > roll_size:
                #     log.debug(f"clipping {len(rolling_xp_list)} is too many.  {rolling_xp_list}")
                #     rolling_xp_list.pop(0)

                previous_event = event_time

            samples_timestamp = []
            samples_xp = []
            samples_inf = []
            for row in raw_samples:
                log.debug(f"{row=}")
                #event, xp, inf = row
                samples_timestamp.append(row.event_time)
                samples_xp.append(row.xp_gain)
                samples_inf.append(row.inf_gain)
                        
            oldest = datetime.strptime(samples[0][0], "%Y-%m-%d %H:%M:%S") 
            newest = datetime.strptime(samples[-1][0], "%Y-%m-%d %H:%M:%S")

            log.debug(f"drawing graph between {oldest} and {newest}")

            duration = (newest - oldest).total_seconds()
            if duration == 0:
                return

            # avg_xp_per_minute = 60 * sum_xp / duration
            # avg_inf_per_minute = 60 * sum_inf / duration

            # shifting to per minute should push it up to where its
            # visible/interesting (it doesn't)
            # ax.axhline(y=avg_xp_per_minute, color='blue')

            ax.scatter(samples_timestamp, samples_xp, c="darkblue", marker='*')

            # samples
            ax2 = ax.twinx()            
            ax2.scatter(samples_timestamp, samples_inf, c="darkgreen", marker=r'$\$$', s=75)
            #ax2.axhline(y=avg_inf_per_minute, color='green')

            log.debug(f'Plotting:\n\n [{len(data_timestamp)}]{data_timestamp=}\n{data_xp=}\n[{len(rolling_data_xp)}]{rolling_data_xp=}\n')
            try:
                ax.plot(data_timestamp, data_xp, drawstyle="steps", color='blue')  
                ax.plot(data_timestamp, rolling_data_xp, 'o--', color='blue')

                ax2.plot(data_timestamp, data_inf, drawstyle="steps", color='green')
            except Exception as err:
                log.error(err)
                log.error("ERROR!!! %s/%s/%s", data_timestamp, data_xp, rolling_data_xp)
        
            ## Set time format and the interval of ticks (every 15 minutes)
            xformatter = md.DateFormatter('%H:%M')
            xlocator = md.MinuteLocator(interval = 1)

            ## Set xtick labels to appear every 15 minutes
            ax.xaxis.set_major_locator(xlocator)

            ## Format xtick labels as HH:MM
            # pyplot.gcf().axes[0].xaxis.set_major_formatter(xformatter)

            #start, end = ax.get_xlim()
            #ax.xaxis.set_ticks(np.arange(start, end, 1))

            # why?  glad you asked.  rewards tend to be both xp and inf, and the
            # ratio of xp to inf is pretty steady.  Since each has its own
            # scale, and they autoscale, the graphs end up overlapping.  a LOT.
            # this 90% scaling on the inf graph should have it track xp, but a little below.
            # ax2.set(
            #     xlim=ax2.get_xlim(), 
            #     ylim=(ax2.get_ylim()[0], 
            #           ax2.get_ylim()[0] * 0.95
            #     )
            # )

            # creating the Tkinter canvas 
            # containing the Matplotlib figure 
            canvas = FigureCanvasTkAgg(
                fig, 
                master = self
            )   
            canvas.draw()         
            canvas.get_tk_widget().pack(fill="both", expand=True)
            log.debug('graph constructed')      

class CharacterTab(ttk.Frame):
    def __init__(self, parent, event_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        self.name = tk.StringVar()
        self.chatter = voice_editor.Chatter(self, event_queue)
        self.chatter.pack(side="top", fill="x")

        self.set_hero()
        # self.xp_chart = ChartFrame(self, self.chatter.hero, 'xp')
        # self.xp_chart.pack(side="top", fill="both", expand=True)

        #self.inf_chart = ChartFrame(self, self.chatter.hero, 'inf')
        #self.inf_chart.pack(side="top", fill="both", expand=True)

    def set_hero(self, *args, **kwargs):
        log.debug(f'set_hero({self.chatter.hero})')
        if hasattr(self, "xp_chart"):
            self.xp_chart.pack_forget()

        try:
            self.xp_chart = ChartFrame(self, self.chatter.hero)
            self.xp_chart.pack(side="top", fill="both", expand=True)
        except Exception as err:
            log.error(err)

        # if hasattr(self, "inf_chart"):
        #     self.inf_chart.pack_forget()

        # self.inf_chart = ChartFrame(self, self.chatter.hero, 'inf')
        # self.inf_chart.pack(side="top", fill="x", expand=True)

        # character.pack(side="top", fill="both", expand=True)

    # character.name.trace_add('write', set_hero)
  

class VoicesTab(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside=None
        self.listside=None

    def get_selected_character(self):
        if (self.detailside is None or self.listside is None):
            for child in self.winfo_children():
                if child.winfo_name() == "!detailside":
                    log.info('Found detailside')
                    self.detailside = child
                elif child.winfo_name() == "!listside":
                    log.info('Found listside')
                    self.listside = child
                else:
                    log.info(f'{child.winfo_name()=}')
        
        #if self.listside:
            #log.info(dir(self.listside))
            #log.info(f"{self.listside=}")

        #if self.detailside:
        #    log.info(dir(self.detailside))
        #    log.info(f"{self.detailside=}")

        # returns a Character() object for the
        # currently selected npc or player.
        if self.listside:
            category, name, _ = self.listside.selected_category_and_name()
            with models.db() as session:
                character = models.Character.get(name, category, session)
            return character
        else:
            return None

class ConfigurationTab(ttk.Frame):
    tkdict = {}

    def elevenlabs_token_frame(self):
        elevenlabs = ttk.Frame(
            self, 
            borderwidth=1, 
            relief="groove"
        )
        ttk.Label(
            elevenlabs,
            text="ElevenLabs API Token",
            anchor="e",
        ).pack(side="left", fill="x", expand=True)
        
        self.elevenlabs_key = tk.StringVar(value=self.get_elevenlabs_key())
        self.elevenlabs_key.trace_add('write', self.change_elevenlabs_key)
        ttk.Entry(
            elevenlabs,
            textvariable=self.elevenlabs_key,
            show="*"
        ).pack(side="left", fill="x", expand=True)
        return elevenlabs

    def polymorph(self, a, b, c):
        """
        Given a config change through the UI, persist it.  Easy.
        """
        log.warning('Polymorph is a dangerous and powerful thing')
        for key in self.tkdict:
            value = self.tkdict[key].get()
            # settings is smart enough to only write to disk when there is
            # a change so this is much better than worst case.
            settings.set_config_key(key, value)
        return

    def get_tkvar(self, tkvarClass, category, system, tag):
        """
        There is a tkvarClass instance located at category/system/tag.
        Instantiate it, give it the right value, hand it back.
        """
        key = f'{category}_{system}_{tag}'
        tkvar = self.tkdict.get(key)
        if tkvar is None:
            tkvar = tkvarClass(
                value=settings.get_config_key(key, False)  # False is sus.
            )
            tkvar.trace_add(
                'write', self.polymorph
            )
            self.tkdict[key] = tkvar

        return tkvar

    def normalize_prompt_frame(self, parent, category):
        """
        frame with ui for the normalize checkbox
        """
        frame = ttk.Frame(parent)
        ttk.Label(
            frame,
            text="Normalize all voices",
            anchor="e",
        ).grid(column=0, row=1)

        tk.Checkbutton(
            frame,
            variable=self.get_tkvar(tk.BooleanVar, category, 'engine', 'normalize')
        ).grid(column=1, row=1)
        return frame
              
    def engine_priorities_frame(self, category):
        """
        the whole config frame for a particular category of entity within the game.
        npc/player/system
        """
        frame = ttk.Frame(
            self,
            borderwidth=1, 
            relief="groove"
        )

        ttk.Label(
            frame,
            text=f"{category}",
            anchor="e",
        ).pack(side="top")

        primary_engine = self.choose_engine(
            frame,
            "Primary Engine",
            self.get_tkvar(tk.StringVar, category, 'engine', 'primary')
        )
        primary_engine.pack(side="top")

        secondary_engine = self.choose_engine(
            frame,
            "Secondary Engine",
            self.get_tkvar(tk.StringVar, category, 'engine', 'secondary')
        )
        secondary_engine.pack(side="top")

        # tkvar = self.get_tkvar(tk.BooleanVar, category, 'engine', 'normalize')
        self.normalize_prompt_frame(frame, category).pack(side="top")

        return frame

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.elevenlabs_token_frame().pack(side="top", fill="x")
       
        self.engine_priorities_frame("npc").pack(side="top", fill="x")
        self.engine_priorities_frame("player").pack(side="top", fill="x")
        self.engine_priorities_frame("system").pack(side="top", fill="x")
        
    def choose_engine(self, parent, prompt, engine_var):
        frame = ttk.Frame(
            parent, 
        )
        ttk.Label(
            frame,
            text=prompt,
            anchor="e",
        ).grid(column=0, row=0)

        default_engine_combo = ttk.Combobox(frame, textvariable=engine_var)
        default_engine_combo["values"] = [e.cosmetic for e in engines.ENGINE_LIST]
        default_engine_combo["state"] = "readonly"
        default_engine_combo.grid(column=1, row=0)

        return frame

    def change_elevenlabs_key(self, a, b, c):
        with open("eleven_labs.key", 'w') as h:
            h.write(self.elevenlabs_key.get())

    def get_elevenlabs_key(self):
        keyfile = 'eleven_labs.key'
        value = None

        if os.path.exists(keyfile):
            with open(keyfile, 'r') as h:
                value = h.read()
        return value

    def change_default_engine(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_ENGINE',
            self.default_engine.get()
        )

    def change_default_engine_normalize(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_ENGINE_NORMALIZE',
            self.default_engine_normalize.get()
        )

    def change_default_player_engine(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_PLAYER_ENGINE',
            self.default_player_engine.get()
        )        

    def change_default_player_engine_normalize(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_PLAYER_ENGINE_NORMALIZE',
            self.default_player_engine_normalize.get()
        )


EXIT = False

def main():
    root = tk.Tk()  

    def on_closing():
        global EXIT
        EXIT = True
        log.info('Exiting...')
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.iconbitmap("sidekick.ico")

    root.geometry("640x640+200+200")
    root.resizable(True, True)
    root.title("City of Heroes Sidekick")

    notebook = ttk.Notebook(root)
    event_queue = multiprocessing.Queue()

    character = CharacterTab(notebook, event_queue)
    character.pack(side="top", fill="both", expand=True)
    notebook.add(character, text='Character')  

    voices = VoicesTab(notebook)
    
    voices.pack(side="top", fill="both", expand=True)
    notebook.add(voices, text='Voices')

    configuration = ConfigurationTab(notebook)
    configuration.pack(side="top", fill="both", expand=True)
    notebook.add(configuration, text="Configuration")

    detailside = voice_editor.DetailSide(voices)
    listside = voice_editor.ListSide(voices, detailside)

    listside.pack(side="left", fill=tk.Y, expand=False)
    detailside.pack(side="left", fill="both", expand=True)
    notebook.pack(fill="both", expand=True)

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
            event_action = event_queue.get(block=False)
            # we got an action (no exception)
            log.info('Event Received: %s', event_action)
            key, value = event_action
            
            if key == "SET_CHARACTER":
                log.info('path set_chraracter')
                character.chatter.hero = npc_chatter.Hero(value)
                log.info('Calling set_hero()...')
                character.set_hero()
                last_character_update = datetime.now()
            elif key == "SPOKE":
                # character named value just spoke
                listside.refresh_character_list()
            elif key == "RECHARGED":
                log.info(f'Power {value} has recharged.')
                if value in ["Hasten", ]:
                    if settings.get_config_key('auto_hasten'):
                        # only send keyboard activity to the city of heroes window
                        # if it is not the foreground window do not do anything.
                        foreground_window_handle = GetForegroundWindow()
                        pid = win32process.GetWindowThreadProcessId(foreground_window_handle)
                        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid[1])
                        
                        proc_name = win32process.GetModuleFileNameEx(handle, 0)
                        zone = GetWindowText(foreground_window_handle)
                        log.info(f'{zone=}')

                        if proc_name.split("\\")[-1] == "cityofheroes.exe":
                            log.info('Triggering Hasten')
                            p.press("enter")
                            p.typewrite(f"/powexec_name \"{value}\"\n")
                        else:
                            log.info(f'Not touch the keyboard of {proc_name!r}.  That would be rude.')
                    else:
                        log.info('auto_hasten is disabled')

                # /powexec_name "hasten"
            else:
                log.error('Unknown event_queue key: %s', key)

        except Exception:
            pass
        
        if last_character_update:
            if (datetime.now() - last_character_update) > update_frequency:
                character.set_hero()
                last_character_update = datetime.now()

        root.update_idletasks()
        root.update()


if __name__ == '__main__':

    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    main()