
import logging
import multiprocessing
import tkinter as tk
import json
from datetime import datetime, timedelta

import cnv.database.models as models
import customtkinter as ctk
import matplotlib.dates as mdates
import numpy as np
from cnv.chatlog import npc_chatter
from cnv.lib import settings
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from sqlalchemy import func, select

log = logging.getLogger(__name__)

# when you are level X, how many xp do you need to reach the next level?
xp_table = {
   1: 106,
   2: 337,
   3: 582,
   4: 800,
   5: 1237,
   6: 1575,
   7: 1950,
   8: 2680,
   9: 3125,
   10: 3600,
   11: 4995,
   12: 6405,
   13: 7400,
   14: 9093,
   15: 11184,
   16: 13000,
   17: 15950,
   18: 19200,
   19: 23400,
   20: 28000,
   21: 36000,
   22: 45000,
   23: 56000,
   24: 69300,
   25: 85200,
   26: 108000,
   27: 135000,
   28: 166650,
   29: 203400,
   30: 254000,
   31: 314600,
   32: 386400,
   33: 470600,
   34: 571200,
   35: 701500,
   36: 854700,
   37: 1036600,
   38: 1250200,
   39: 1502550,
   40: 1692900,
   41: 1907550,
   42: 2150550,
   43: 2421900,
   44: 2729700,
   45: 3078000,
   46: 3470850,
   47: 3912300,
   48: 4410450,
   49: 4973400,
   50: 5608000,
}

class ChartFrame(ctk.CTkFrame):
    def get_latest_event(self, hero_id):
        try:
            with models.Session(models.engine) as session:
                latest_event = session.scalars(
                    select(models.HeroStatEvent).where(
                        models.HeroStatEvent.hero_id == hero_id
                    ).order_by(
                        models.HeroStatEvent.event_time.desc()
                    )
                ).first()
        except Exception as err:
            log.error('Unable to determine latest event')
            log.error(err)
            raise

        return latest_event

    def get_raw_samples(self, hero_id, start_time, end_time, session):
        log.debug('Gathering raw samples')
        try:
            raw_samples = session.scalars(
                select(
                    models.HeroStatEvent
                ).where(
                    models.HeroStatEvent.hero_id == hero_id,
                    models.HeroStatEvent.event_time >= start_time,
                    models.HeroStatEvent.event_time <= end_time,
                )
            ).all()
        except Exception as err:
            log.error('Error gathering data samples')
            log.error(err)
            raise

        return raw_samples
    
    def get_binned_samples(self, hero_id, start_time, end_time, session):
        # do some binning in per-minute buckets in the database.
        log.debug('Gathering binned samples')

        try:
            samples = session.execute(
                select(
                    func.STRFTIME('%Y-%m-%d %H:%M:00', models.HeroStatEvent.event_time).label('EventMinute'),
                    func.sum(models.HeroStatEvent.xp_gain).label('xp_gain'),
                    func.sum(models.HeroStatEvent.inf_gain).label('inf_gain')
                ).where(
                    models.HeroStatEvent.hero_id == hero_id,
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

        return samples

    def __init__(self, parent, hero, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        log.debug('Initializing ChartFrame()')
        if not hero:
            return
        else:
            log.debug(f'Drawing graph for {hero}')
            self.hero = hero

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
        
            # find the most recent event to determine the timestamp for the
            # right edge of the graph.
            latest_event = self.get_latest_event(self.hero.id)
            log.debug(f'latest_event: {latest_event}')

            if latest_event:
                end_time = latest_event.event_time
            else:
                log.debug(f'No previous events found for {self.hero.name}')
                end_time = datetime.now()

            # the left edge is two hours before the right edge.
            start_time = end_time - timedelta(minutes=120)
            log.debug(f'Graphing xp gain between {start_time} and {end_time}')

            with models.db() as session:
                raw_samples = self.get_raw_samples(
                    hero.id, start_time, end_time, session
                )
                binned_samples = self.get_binned_samples(
                    hero.id, start_time, end_time, session
                )

            log.debug(f'Found {len(binned_samples)} binned samples, {len(raw_samples)} raw values')

            data_timestamp = []
            data_xp = []
            data_inf = []
            rolling_data_xp = []
            rolling_xp_list = []
            roll_size = 5
            previous_event = None
            sum_xp = 0
            sum_inf = 0

            for row in binned_samples:
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

                if xp_gain is None:
                    xp_gain = 0

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
                samples_timestamp.append(row.event_time)
                samples_xp.append(row.xp_gain)
                samples_inf.append(row.inf_gain)
            
            log.debug(f"drawing graph between {start_time} and {end_time}")

            # scatter plot of each actual XP gain event with a blue star
            ax.scatter(samples_timestamp, samples_xp, c="darkblue", marker='*')

            # left axis label
            ax.set_ylabel('Experience')

            # second axis for influence gain
            ax2 = ax.twinx()

            # right axis label
            ax2.set_ylabel('Influence')
            # scatter plot for each INF gain event with a green $
            ax2.scatter(samples_timestamp, samples_inf, c="darkgreen", marker=r'$\$$', s=75)

            log.debug(f'Plotting:\n\n [{len(data_timestamp)}]{data_timestamp=}\n{data_xp=}\n[{len(rolling_data_xp)}]{rolling_data_xp=}\n')
            try:
                # binned averages over per-minute time intervals
                ax.plot(data_timestamp, data_xp, drawstyle="steps", color='blue')  
                
                # blue dotted line with discs for the current rolling average
                # over the last five minutes.
                ax.plot(data_timestamp, rolling_data_xp, 'o--', color='blue')

                # binned averages per minute for influence; this is kinda junk since
                # it very (very) frequently lands right on top of the xp bins.
                ax2.plot(data_timestamp, data_inf, drawstyle="steps", color='green')
            except Exception as err:
                log.error(err)
                log.error("ERROR!!! %s/%s/%s", data_timestamp, data_xp, rolling_data_xp)
        
            # labels on the time axis every ten minutes seems about right
            # without too much clutter.
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M'))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=10))

            # do we know what level the character is?
            level = settings.get_config_key(
                'level', default=None, cf='state.json'
            )
            if level:
                # subtle color bands
                xp_needed = xp_table[int(level)]
                
                # the higher your level, the longer a level up is reasonably
                # expected to take.  Lets yank a formula out of our keister.
                typical_time = 10 + (2 * int(level))
                
                # you will level up every half hour, anything faster than that
                # is green.
                typical = int(xp_needed / typical_time)

                # it will take two hours to gain a level
                poor = int(xp_needed / (3 * typical_time))
                
                # green_band
                ax.axhspan(ymin=typical, ymax=ax.get_ylim()[1], facecolor='#00FF00', alpha=0.05)
                # yellow_band
                ax.axhspan(ymin=poor, ymax=typical, facecolor='#FFFF00', alpha=0.05)
                # red_band
                ax.axhspan(ymin=0, ymax=poor, facecolor='#FF0000', alpha=0.05)

            # creating the Tkinter canvas 
            # containing the Matplotlib figure 
            canvas = FigureCanvasTkAgg(
                fig, 
                master = self
            )   
            # this is the only widget in ChartFrame
            canvas.draw()         
            canvas.get_tk_widget().pack(fill="both", expand=True)
            log.debug('graph constructed')      


class TypedDamage:
    def __init__(self, damage_type, special='', count=0, total=0):
        self.damage_type = damage_type
        self.special = special
        self.count = count
        self.total = total


class PowerStat:
    def __init__(self, name):
        self.hit = 0
        self.miss = 0
        self.typed = {}
        self.height = None

        if ':' in name:
            self.name = name.split(':')[0] + " (proc)"
        else:
            self.name = name
    
    def record_damage(self, damage_type:str, special:str, damage:float):
        self.hit += 1

        key = (damage_type, special)
        if key not in self.typed:
            self.typed[key] = TypedDamage(damage_type, special)

        self.typed[key].count += 1
        self.typed[key].total += damage

    def row_height(self):
        if self.height:
            return self.height 
        
        self.height = 0
        for damage_type, special in self.typed:
            if damage_type != "":
                self.height += 1

        if self.height > 1:
            # one more for "all"
            self.height += 1
        return self.height

    def calculate_grid(self):
        self.hits = 0
        self.total_damage = 0
        self.tries = 0        
        
        for damage_type, special in self.typed:
            key = (damage_type, special)
            # misses don't have a damage type
            if damage_type:
                self.hits += self.typed[key].count
            self.tries += self.typed[key].count
            self.total_damage += self.typed[key].total
            
        # Hit Rate
        self.perc = 100 * float(self.hits) / float(self.tries)

    def draw_grid_row(self, parent, row_index):
        self.height = self.row_height()
        # Power Name
        ctk.CTkLabel(
            parent,
            text=self.name
        ).grid(
            column=0, 
            row=row_index,
            rowspan=self.height,
            sticky="ew", 
            padx=5
        )        

        # Hit Rate
        ctk.CTkLabel(
            parent, 
            text=f"{self.hits} of {self.tries}: {self.perc:0.2f}%"
        ).grid(
            column=1, 
            row=row_index,
            rowspan=self.height
        )

        # for the the per-damage type, grid-within-grid
        def draw_damage_type_grid(typed_damage, row_index):
            
            # Type
            ctk.CTkLabel(
                parent, text=typed_damage.damage_type, corner_radius=0, padx=0
            ).grid(column=2, row=row_index)

            # Special
            ctk.CTkLabel(
                parent, text=typed_damage.special, corner_radius=0, padx=0
            ).grid(column=3, row=row_index)

            # Average
            ctk.CTkLabel(
                parent, 
                text=f"{typed_damage.total / typed_damage.count:,.2f}",
                corner_radius=0, padx=0
            ).grid(column=4, row=row_index)

            # Total
            ctk.CTkLabel(
                parent, text=f"{typed_damage.total:,}",
                corner_radius=0, padx=0
            ).grid(column=5, row=row_index)

        count = 0
        for damage_type, special in self.typed:
            count += 1

            key = (damage_type, special)
            if damage_type:
                typed_damage = self.typed[key]
                draw_damage_type_grid(typed_damage, row_index)
                row_index += 1
        
        if count > 1:
            # multiple damage types, we add some cosmetics and a 'Total' row to
            # show aggregate stats from all types.
            total_damage = TypedDamage('Total', count=self.hits, total=self.total_damage)
            
            hline = tk.Frame(parent, borderwidth=1, relief="solid", height=1)
            hline.grid(column=2, row=row_index, columnspan=4, sticky="ew")
            row_index += 1

            draw_damage_type_grid(total_damage, row_index)
        
        # the _next_ row available
        return row_index


class DamageFrame(ctk.CTkScrollableFrame):
    """
    Damage is different than XP/Inf.  I'm not interested in rates or projections.
    I want to know how much damage each power is doing and how often I use them.
    We will scope to this session, so we will do this in memory.
    """
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.create_grid_header()
        
    def create_grid_header(self):
        self.grid_rowconfigure(0, weight=0)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Power Name").grid(column=0, row=0, sticky='ew')

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Hit Rate").grid(column=1, row=0, sticky='ew')

        self.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(self, text="Type").grid(column=2, row=0, sticky='ew')
        
        self.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(self, text="Special").grid(column=3, row=0, sticky='ew')
        
        self.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(self, text="Average").grid(column=4, row=0, sticky='ew')
        
        self.grid_columnconfigure(5, weight=1)
        ctk.CTkLabel(self, text="Total").grid(column=5, row=0, sticky='ew')

        hline = tk.Frame(self, borderwidth=1, relief="solid", height=2)
        hline.grid(column=0, row=1, columnspan=6, sticky="ew")
        
        # how many grid rows we occupy
        return 2    

    def refresh_damage_panel(self):
        log.debug("refresh_damage_panel")
        # clear any old data
        for widget in self.winfo_children():
            widget.destroy()
        row_index = self.create_grid_header()

        # how much of the math in python vs sqlite?
        with models.db() as session:
            all_damage = session.scalars(
                select(models.Damage)
            ).all()

        powers = {}
        for row in all_damage:
            if row.power not in powers:
                powers[row.power] = PowerStat(name=row.power)

            power = powers[row.power]     
            power.record_damage(row.damage_type, row.special, row.damage)

        for powername in powers:
            power = powers[powername]
            # calcualte the totals for every power so we have something to sort by
            power.calculate_grid()

        for powername in sorted(powers, key=lambda p: powers[p].total_damage, reverse=True):
            power = powers[powername]
            
            # draw the grid to self in grid row `row_index`
            row_index = power.draw_grid_row(self, row_index)

            # horizontal line between each power
            hline = tk.Frame(self, borderwidth=1, relief="groove", height=2)
            hline.grid(column=0, row=row_index + 1, columnspan=6, sticky="ew")

            row_index += 2


class ChatterService:
    def start(self, event_queue, speaking_queue):
        log.info('ChatterService.start()')
        
        npc_chatter.TightTTS(speaking_queue, event_queue)
        speaking_queue.put((None, "Attaching to most recent log...", 'system'))

        logdir = "G:/CoH/homecoming/accounts/VVonder/Logs"
        badges = True
        team = True
        npc = True

        ls = npc_chatter.LogStream(
            logdir, speaking_queue, event_queue, badges, npc, team
        )
        while True:
            ls.tail()


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
        
        self.logdir = tk.StringVar(
            value=settings.get_config_key('logdir', default='')
        )
        self.logdir.trace_add('write', self.save_logdir)

        # expand the entry box
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)

        ctk.CTkButton(
            self, 
            textvariable=self.button_text, 
            command=self.attach_chatter
        ).grid(column=0, row=0)

        ctk.CTkEntry(
            self, 
            textvariable=self.logdir
        ).grid(column=1, row=0, sticky="ew")
         
        ctk.CTkButton(
            self,
            text="Set Log Dir",
            command=self.ask_directory
        ).grid(column=2, row=0)
        
        self.cs = ChatterService()

    def save_logdir(self, *args):
        logdir = self.logdir.get()
        log.debug(f'Persisting setting logdir={logdir}')
        settings.set_config_key('logdir', logdir)

    def ask_directory(self):
        dirname = tk.filedialog.askdirectory()
        self.logdir.set(dirname)

    def attach_chatter(self):
        """
        Not sure exactly how I want to do this.  I think the best long term
        option is to just launch a process and be done with it.
        """

        if self.attached:
            # we are already attached, I guess we want to stop.
            self.p.terminate()
            self.button_text.set(self.attach_label)
            self.attached = False
            log.debug('Detached')
        else:
            # we are not attached, lets do that.
            self.attached = True
            self.button_text.set(self.detach_label)
            self.p = multiprocessing.Process(
                target=self.cs.start, 
                args=(
                    self.event_queue,
                    self.speaking_queue,
                )
            )
            self.p.start()
            log.debug('Attached')


class CharacterTab(ctk.CTkFrame):
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        hero = models.get_hero()
        
        #self.update_xpinf()
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        # self.rowconfigure(2, weight=1)

        self.name = tk.StringVar()
        self.chatter = Chatter(self, event_queue, speaking_queue)
        self.chatter.grid(column=0, row=0, sticky="nsew")

        self.total_exp = tk.IntVar(value=0)
        self.total_inf = tk.IntVar(value=0)
        
        buffer = ctk.CTkFrame(self)
        buffer.grid_rowconfigure(0, weight=1)
        buffer.grid_columnconfigure(0, weight=1)
        self.character_subtabs = ctk.CTkTabview(
            buffer, anchor="nw", height=512, command=self.subtab_selected
        )

        self.graph = self.character_subtabs.add('Graph')
        self.graph.grid_columnconfigure(0, weight=1)
        self.graph.grid_rowconfigure(0, weight=1)
        ChartFrame(self.graph, hero).grid(column=0, row=0, sticky="nsew")

        damage = self.character_subtabs.add('Damage')
        damage.grid_columnconfigure(0, weight=1)
        damage.grid_rowconfigure(0, weight=1)

        self.damageframe = DamageFrame(damage)
        self.damageframe.grid(column=0, row=0, sticky="nsew")

        # experience = self.character_subtabs.add('Experience')
        # influence = self.character_subtabs.add('Influence')

        self.character_subtabs.grid(column=0, row=0, sticky="nsew")
        buffer.grid(column=0, row=1, sticky="nsew")

        self.start_time = datetime.now()
        
    def subtab_selected(self, *args, **kwargs):
        selected_tab = self.character_subtabs.get()
        if selected_tab == "Damage":
            self.damageframe.refresh_damage_panel()
            self.damageframe.pack(fill="both", expand=True)
        elif selected_tab == "Graph":
            pass
        else:
            log.warning(f'Unknown tab: {selected_tab}')


    def update_xpinf(self):
        hero_id = settings.get_config_key('hero_id', cf='state.json')

        with models.db() as session:
            try:
                total_exp, total_inf = session.query(
                    func.sum(models.HeroStatEvent.xp_gain),
                    func.sum(models.HeroStatEvent.inf_gain)
                    ).where(
                        models.HeroStatEvent.hero_id == hero_id,
                        models.HeroStatEvent.event_time >= self.start_time
                ).all()[0]  # first (only) row
            except IndexError:
                total_exp = 0
                total_inf = 0
            
            self.total_exp.set(total_exp)
            self.total_inf.set(total_inf)


    def set_progress_chart(self, *args, **kwargs):
        """
        Invoked at init(), but also whenever the character changes (logout to character select)
        and more critically, every N seconds to refresh the graph.
        """
        hero = models.get_hero()

        if hasattr(self, "progress_chart"):
            self.progress_chart.grid_forget()
            #self.total_exp.set(0)
            #self.total_inf.set(0)
        try:
            self.update_xpinf()
        except Exception as err:
            log.error(err)

        try:
            self.damageframe.refresh_damage_panel()
        except Exception as err:
            log.error(err)

        self.progress_chart = ChartFrame(self.graph, hero)
        self.graph.grid_columnconfigure(0, weight=1)
        self.graph.grid_rowconfigure(0, weight=1)
        self.progress_chart.grid(column=0, row=0, sticky="nsew")
