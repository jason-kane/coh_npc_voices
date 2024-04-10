"""
There is more awesome to be had.
"""

"""Hello World application for Tkinter"""

import logging
import multiprocessing
import os
from datetime import datetime, timedelta
import queue
import sys
import tkinter as tk
from tkinter import font, ttk
from sqlalchemy import func, select
import db
import effects
import engines
import models

import voice_editor
import npc_chatter
from pedalboard.io import AudioFile
from voicebox.sinks import Distributor, SoundDevice, WaveFile

from matplotlib import pyplot
from matplotlib.figure import Figure 
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,  
    NavigationToolbar2Tk
) 

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

class ChartFrame(tk.Frame):
    def __init__(self, parent, hero, category, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.category = category

        if not hero:
            return
        else:
            log.info(f'Drawing graph for {hero}')
            self.hero = hero
            # draw graph for $category progress, total per/minute
            # binned to the minute for the last hour.

            # the figure that will contain the plot 
            fig = Figure(
                figsize = (5, 5), 
                dpi = 100
            ) 
        
            # list of squares 
            # y = [i**2 for i in range(101)] 
        
            # adding the subplot 
            plot1 = fig.add_subplot(111) 
        
            # plotting the graph 
            # plot1.plot(y) 
            #data = get_total_xp(starttime, endtime, bin_size=60)
            # cursor = db.get_cursor()

            # end time should be the most recent timestamp
            # not now()
            log.info(f'Retrieving {self.category} data')
            with models.Session(models.engine) as session:
                latest_event = session.scalar(
                    select(models.HeroStatEvent).where(
                        models.HeroStatEvent.hero == self.hero.id
                    ).order_by(
                        models.HeroStatEvent.event_time.desc
                    )
                ).first()
            
            log.info(f'latest_event: {latest_event}')

            if latest_event:
                end_time = latest_event.event_time
            else:
                log.info(f'No previous events found for {self.hero.name}')
                end_time = datetime.now()

            start_time = end_time - timedelta(minutes=60)
            log.info(f'Graphing {self.category} gain between {start_time} and {end_time}')

            with models.Session(models.engine) as session:
                samples = session.scalar(
                    select(
                        func.STRFTIME('%Y-%m-%d %H:%M:00', models.HeroStatEvent.event_time),
                        func.sum(models.HeroStatEvent.xp_gain),
                        func.sum(models.HeroStatEvent.inf_gain),
                        models.HeroStatEvent
                    ).where(
                        models.HeroStatEvent.hero == self.hero.id,
                        models.HeroStatEvent.event_time >= start_time,
                        models.HeroStatEvent.event_time <= end_time,
                    ).group_by(
                        func.STRFTIME('%Y-%m-%d %H:%M:00', models.HeroStatEvent.event_time)
                    ).order_by(
                        models.HeroStatEvent.event_time
                    )
                ).all()
            # try:
            #     samples = cursor.execute("""
            #         SELECT
            #             STRFTIME('%Y-%m-%d %H:%M:00', event_time) as EventMinute,
            #             SUM(xp_gain),
            #             SUM(inf_gain)
            #         FROM 
            #             hero_stat_events
            #         WHERE
            #             hero = ? AND
            #             event_time > ? AND
            #             event_time <= ?
            #         GROUP BY
            #             STRFTIME('%Y-%m-%d %H:%M:00', event_time)
            #         ORDER BY
            #             EventMinute
            #     """, (self.hero.id, start_time, end_time)).fetchall()
            # except Exception as err:
            #     log.error(err)
            #     raise
            
            log.info(f'Found {len(samples)} samples')

            data_x = []
            data_y = []
            
            for row in samples:
                data_x.append(
                    row.event_time
                    # datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                )
                # log.info(row)

                if self.category == "xp":
                    data_y.append(row.xp_gain)
                    # row[1])
                elif self.category == "inf":
                    data_y.append(row.inf_gain)
                    # row[2])
                
            log.info(f'Plotting {data_x}:{data_y}')
            # data = ((0, 1), (1, 10), (2, 10), (3, 500), (5, 200))
            plot1.plot(data_x, data_y)
        
            # creating the Tkinter canvas 
            # containing the Matplotlib figure 
            canvas = FigureCanvasTkAgg(
                fig, 
                master = self
            )   
            canvas.draw() 
        
            # placing the canvas on the Tkinter window 
            canvas.get_tk_widget().pack() 
        
            # creating the Matplotlib toolbar 
            toolbar = NavigationToolbar2Tk(
                canvas, 
                self
            ) 
            toolbar.update() 
        
            # placing the toolbar on the Tkinter window 
            canvas.get_tk_widget().pack()
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

        self.xp_chart = ChartFrame(self, self.chatter.hero, 'xp')
        self.xp_chart.pack(side="top", fill="x", expand=True)

        if hasattr(self, "inf_chart"):
            self.inf_chart.pack_forget()

        self.inf_chart = ChartFrame(self, self.chatter.hero, 'inf')
        self.inf_chart.pack(side="top", fill="x", expand=True)

        # character.pack(side="top", fill="both", expand=True)

    # character.name.trace_add('write', set_hero)
    


def main():
    root = tk.Tk()
    # root.iconbitmap("myIcon.ico")
    root.geometry("640x480+200+200")
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