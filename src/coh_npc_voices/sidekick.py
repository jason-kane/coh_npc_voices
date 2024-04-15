"""
There is more awesome to be had.
"""
import logging
import multiprocessing
from datetime import datetime, timedelta
import sys
import tkinter as tk
from tkinter import font, ttk
from sqlalchemy import func, select
import models
import matplotlib.dates as mdates
import voice_editor
import npc_chatter
import numpy as np

from matplotlib.figure import Figure 
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,  
    NavigationToolbar2Tk
) 

import ctypes
# this unlinks us from python so windows will
# use our icon instead of the python icon in the
# taskbar.
myappid = u'fun.side.projects.sidekick.1.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

class ChartFrame(tk.Frame):
    def __init__(self, parent, hero, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        if not hero:
            return
        else:
            log.info(f'Drawing graph for {hero}')
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
            log.info(f'Retrieving {self.category} data')
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
            
            log.info(f'latest_event: {latest_event}')

            if latest_event:
                end_time = latest_event.event_time
            else:
                log.info(f'No previous events found for {self.hero.name}')
                end_time = datetime.now()

            start_time = end_time - timedelta(minutes=120)
            log.info(f'Graphing {self.category} gain between {start_time} and {end_time}')

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
            
            log.info(f'Found {len(samples)} samples')

            data_x = []
            data_y = []
            rolling_data_y = []
            last_n = []
            roll_size = 5
            for row in samples:
                log.info(f'row: {row}')
                datestring, xp_gain, inf_gain = row
                event_time = datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S") 
                
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

                    if len(last_n) > roll_size:
                        log.info(f"clipping {len(last_n)} is too many.  {last_n}")
                        last_n.pop(0)

                elif self.category == "inf":
                    data_x.append(event_time)
                    data_y.append(inf_gain)

            log.info(f'Plotting {data_x}:{data_y}/{rolling_data_y}')
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
            log.info('graph constructed')      

class CharacterTab(tk.Frame):
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
    

def main():
    root = tk.Tk()
    root.iconbitmap("sidekick.ico")

    root.geometry("640x640+200+200")
    root.resizable(True, True)
    root.title("City of Heroes Sidekick")

    notebook = ttk.Notebook(root)
    event_queue = multiprocessing.Queue()

    character = CharacterTab(notebook, event_queue)
    character.pack(side="top", fill="both", expand=True)
    notebook.add(character, text='Character')  

    voices = tk.Frame(notebook)
    voices.pack(side="top", fill="both", expand=True)
    notebook.add(voices, text='Voices')

    with models.Session(models.engine) as session:
        first_character = session.query(models.Character).order_by(models.Character.name).first()

    if first_character:
        selected_character = tk.StringVar(value=f"{first_character.cat_str()} {first_character.name}")
    else:
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

    while True:
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