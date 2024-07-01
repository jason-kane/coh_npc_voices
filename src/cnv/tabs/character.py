
import logging
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import cnv.database.models as models
import cnv.voices.voice_editor as voice_editor
import matplotlib.dates as mdates
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from sqlalchemy import func, select

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
            fig.tight_layout(pad=0.01)

            # adding the subplot 
            ax = fig.add_subplot(111)
            ax.margins(x=0, y=0)
            ax.tick_params(axis='x', rotation=60)
        
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
                log.debug(f'No previous events found for {self.hero.name}')
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

                previous_event = event_time

            samples_timestamp = []
            samples_xp = []
            samples_inf = []
            for row in raw_samples:
                # log.debug(f"{row=}")
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

            ax.set_ylabel('Experience')
            # samples
            ax2 = ax.twinx()
            ax2.set_ylabel('Influence')
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
        
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M'))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=10))

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
        self.chatter.pack(side="top", fill=tk.X)

        self.total_exp = tk.IntVar(value=0)
        self.total_inf = tk.IntVar(value=0)
        
        totals_frame = self.totals_frame()
        totals_frame.pack(side="top", fill=tk.X, expand=False)

        self.start_time = datetime.now()
        self.set_hero()

    def totals_frame(self):
        """
        Frame for displaying xp and influence totals
        """
        frame = ttk.Frame(self)
        ttk.Label(frame, text="Experience").pack(side="left")
        ttk.Label(frame, textvariable=self.total_exp).pack(side="left")
        ttk.Label(frame, text="Influence").pack(side="left")
        ttk.Label(frame, textvariable=self.total_inf).pack(side="left")
        return frame

    def update_xpinf(self):
        with models.db() as session:
            total_exp, total_inf = session.query(
                func.sum(models.HeroStatEvent.xp_gain),
                func.sum(models.HeroStatEvent.inf_gain)
                ).where(
                    models.HeroStatEvent.hero_id == self.chatter.hero.id,
                    models.HeroStatEvent.event_time >= self.start_time
            ).all()[0]  # first (only) row
            
            self.total_exp.set(total_exp)
            self.total_inf.set(total_inf)


    def set_hero(self, *args, **kwargs):
        """
        Invoked at init(), but also whenever the character changes (logout to character select)
        and more critically, every N seconds to refresh the graph.
        """
        log.debug(f'{self.chatter=}')
        log.debug(f'set_hero({self.chatter.hero})')

        if hasattr(self, "progress_chart"):
            self.progress_chart.pack_forget()
            self.total_exp.set(0)
            self.total_inf.set(0)
        try:
            self.update_xpinf()
            self.progress_chart = ChartFrame(self, self.chatter.hero)
            self.progress_chart.pack(side="top", fill="both", expand=True)
        except Exception as err:
            log.error(err)
