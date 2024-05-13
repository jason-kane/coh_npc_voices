"""
There is more awesome to be had.
"""
import logging
from logging.config import dictConfig
import multiprocessing
from datetime import datetime, timedelta
import sys
import tkinter as tk
from tkinter import ttk
from sqlalchemy import func, select
import models
import matplotlib.dates as mdates
import voice_editor
import npc_chatter
import numpy as np
import settings
import engines

from matplotlib.figure import Figure 
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg
) 

import ctypes
# this unlinks us from python so windows will
# use our icon instead of the python icon in the
# taskbar.
myappid = u'fun.side.projects.sidekick.1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

LOGGING_CONFIG = { 
    'version': 1,
    'disable_existing_loggers': True,
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
            'propagate': False
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

log = logging.getLogger("__name__")

class ChartFrame(ttk.Frame):
    def __init__(self, parent, hero, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

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

            with models.Session(models.engine) as session:
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
            
            log.debug(f'Found {len(samples)} samples')

            data_x = []
            data_y = []
            rolling_data_y = []
            last_n = []
            roll_size = 5
            last_event = None

            for row in samples:
                # log.info(f'row: {row}')
                datestring, xp_gain, inf_gain = row
                event_time = datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S") 
                while last_event and (event_time - last_event) > timedelta(minutes=1, seconds=30):
                    # We have a time gap; fill it with zeroes
                    new_event_time = last_event + timedelta(minutes=1)
                    data_x.append(new_event_time)
                    data_y.append(0)
                    last_n.append(0)
                    last_event = new_event_time
                
                if self.category == "xp":
                    if xp_gain is None:
                        continue

                    data_x.append(event_time)
                    data_y.append(xp_gain)
                    last_n.append(xp_gain)

                    try:
                        rolling_data_y.append(np.mean(last_n))
                    except Exception as err:
                        log.error(err)
                        log.error(f'last_n: {last_n}')
                        raise

                    while len(last_n) > roll_size:
                        log.debug(f"clipping {len(last_n)} is too many.  {last_n}")
                        last_n.pop(0)

                elif self.category == "inf":
                    data_x.append(event_time)
                    data_y.append(inf_gain)
                    .00

            # log.info(f'Plotting {data_x}:{data_y}/{rolling_data_y}')
            try:
                ax.plot(data_x, data_y, drawstyle="steps", label=f"{self.category}")
                ax.plot(data_x, rolling_data_y, 'o--')
            except Exception as err:
                log.error(err)
                log.error(data_x, data_y, rolling_data_y)
        
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
        log.info(f'set_hero({self.chatter.hero})')
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

        # self.default_engine = tk.StringVar(
        #     value=settings.get_config_key('DEFAULT_ENGINE', "Windows TTS")
        # )
        # self.default_engine.trace_add('write', self.change_default_engine)

        # self.default_engine_normalize = tk.BooleanVar(
        #     value=settings.get_config_key('DEFAULT_PLAYER_ENGINE_NORMALIZE', False)
        # )
        # self.default_engine_normalize.trace_add(
        #     'write', self.change_default_engine_normalize
        # )

        # ####
        # ####
        # self.default_player_engine = tk.StringVar(
        #     value=settings.get_config_key('DEFAULT_PLAYER_ENGINE', "Windows TTS")
        # )
        # self.default_player_engine.trace_add('write', self.change_default_player_engine)


        # default_player_engine = self.choose_engine(
        #     "Default Player Engine",
        #     self.default_player_engine,
        #     self.default_player_engine_normalize,
        # )
        
        # default_player_engine.pack(side="top", fill="x")
        
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

        # ttk.Label(
        #     frame,
        #     text=f"Normalize {prompt}",
        #     anchor="e",
        # ).grid(column=0, row=1)

        # tk.Checkbutton(
        #     frame,
        #     variable=normalize_var
        # ).grid(column=1, row=1)

        return frame

    def change_elevenlabs_key(self, a, b, c):
        with open("eleven_labs.key", 'w') as h:
            h.write(self.elevenlabs_key.get())

    def get_elevenlabs_key(self):
        with open('eleven_labs.key', 'r') as h:
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

    voices = ttk.Frame(notebook)
    voices.pack(side="top", fill="both", expand=True)
    notebook.add(voices, text='Voices')

    configuration = ConfigurationTab(notebook)
    configuration.pack(side="top", fill="both", expand=True)
    notebook.add(configuration, text="Configuration")

    # with models.Session(models.engine) as session:
    #     first_character = session.query(models.Character).order_by(models.Character.name).first()

    #if first_character:
    #    selected_character = tk.StringVar(value=f"{first_character.cat_str()} {first_character.name}")
    #else:
    selected_character = tk.StringVar()

    detailside = voice_editor.DetailSide(voices, selected_character)
    listside = voice_editor.ListSide(voices, detailside)

    listside.pack(side="left", fill="both", expand=True)
    detailside.pack(side="left", fill="both", expand=True)
    notebook.pack(fill="both", expand=True)

    # in the mainloop we want to know if event_queue gets a new
    # entry.
    #root.mainloop()
    last_character_update = None
    
    # update the graph(s) this often
    update_frequency = timedelta(minutes=1)

    while not EXIT:
        try:
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