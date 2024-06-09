"""Voice Editor component"""
import logging
import multiprocessing
import os
import queue
import sys
import tkinter as tk
from tkinter import font, ttk

import db
import effects
import engines
import models
import npc_chatter
import settings
import voicebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from npc import PRESETS
from pedalboard.io import AudioFile
from scipy.io import wavfile
from sqlalchemy import delete, desc, select, update
from tkfeather import Feather
from voicebox.sinks import Distributor, SoundDevice, WaveFile
from voicebox.tts.utils import get_audio_from_wav_file

logging.basicConfig(
    level=settings.LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)
ENGINE_OVERRIDE = {}

#class ChoosePhrase(ttk.Frame):
class WavfileMajorFrame(ttk.LabelFrame):    
    ALL_PHRASES = "< Rebuild all phrases >"
    def __init__(self, parent, detailside, selected_character, *args, **kwargs):
        kwargs['text'] = 'Wavefile(s)'
        super().__init__(parent, *args, **kwargs)
        topline = ttk.Frame(self)
        
        self.selected_character = selected_character
        self.detailside = detailside

        self.chosen_phrase = tk.StringVar(
            value="<Choose or type a phrase>"
        )
        self.chosen_phrase.trace_add('write', self.chose_phrase)
        self.options = ttk.Combobox(
            topline, 
            textvariable=self.chosen_phrase
        )
        self.options["values"] = []

        self.populate_phrases()
        self.options.pack(side="left", fill="x", expand=True)

        # TODO:  there should be two buttons, one to regenerate
        # the file and another to play the file.  The play button
        # is greyed out unless the file exists.  Big UI change: you
        # can regenerate everything for someone that talks a lot
        # without having to wait and listen to them all.  You can
        # also listen to everything a character says, back to back
        # without spending any TTS credits (presuming cached).
        self.play_btn = ttk.Button(topline, text="Play", command=self.play_cache)

        regen_btn = ttk.Button(topline, text="Regen", command=self.say_it)
        regen_btn.pack(side="left")
        self.play_btn.pack(side="left")        

        topline.pack(side="top", expand=True, fill="x")

        self.visualize_wav = None

    def chose_phrase(self, *args, **kwargs):
        # a phrase was chosen.
        raw_name = self.selected_character.get()

        with models.db() as session:
            character = models.get_character_from_rawname(raw_name, session)

            phrase = self.chosen_phrase.get()
            cachefile = self.get_cachefile(character, phrase)

        if os.path.exists(cachefile):
            self.play_btn["state"] = "normal"
            # convert mp3 to wav file
            with AudioFile(cachefile) as input:
                with AudioFile(
                    filename=cachefile + ".wav",
                    samplerate=input.samplerate,
                    num_channels=input.num_channels,
                ) as output:
                    while input.tell() < input.frames:
                        output.write(input.read(1024))

            # and display it
            self.show_wave(cachefile + ".wav")
        else:
            log.info(f'Cached mp3 {cachefile} does not exist.')
            self.clear_wave()
            self.play_btn["state"] = "disabled"
        return

    def populate_phrases(self):
        log.info('** populate_phrases() called **')
        raw_name = self.selected_character.get()

        # pull phrases for this character from the database
        with models.db() as session:            
            character = models.get_character_from_rawname(raw_name, session)
        
            if character is None:
                log.error(f'62 Character {raw_name} does not exist!')
                return

            character_phrases = session.scalars(
                select(models.Phrases).where(
                    models.Phrases.character_id == character.id
                )
            ).all()
       
        if character_phrases:
            # default to the first phrase
            self.chosen_phrase.set(character_phrases[0].text)
        else:
            self.chosen_phrase.set(
                f'I have no record of what {raw_name} says.')
            
        self.options["values"] = [
            p.text for p in character_phrases
        ] + [ self.ALL_PHRASES ]

    def clear_wave(self):
        if hasattr(self, 'canvas'):
            log.info('*** clear_wave() called ***')
            self.plt.clear()
            self.spec.clear()
            self.canvas.draw_idle()

    def show_wave(self, cachefile):
        """
        Visualize a wav file

        # I know, not very efficient to just jam this in here
        # https://learnpython.com/blog/plot-waveform-in-python/
        # https://matplotlib.org/3.1.0/gallery/user_interfaces/embedding_in_tk_sgskip.html        
        """
        sampling_rate, data = wavfile.read(cachefile)
        if self.visualize_wav is None:
            # our widget hasn't been rendered.  Do be a sweetie and take
            # care of that for me.
            self.visualize_wav = ttk.Frame(self, padding = 8)
            self.fig = Figure(
                figsize=(3, 2), # (width, height) figsize in inches (not kidding)
                dpi=100, # but we get dpi too so... sane?
                layout='constrained'
            )  

            self.plt = self.fig.add_subplot(211, facecolor=('xkcd:light grey'))
            self.spec = self.fig.add_subplot(212)
            self.canvas = FigureCanvasTkAgg(self.fig, self.visualize_wav)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)
        else:
            self.clear_wave()

        # if channels == 1:
        self.plt.plot(data)
        self.spec.specgram(data, Fs=sampling_rate)
        self.canvas.draw_idle()

        # elif channels == 2:
        #     self.plt.plot(times, l_channel, label="Left Channel")
        #     self.plt.plot(times, r_channel, label="Right Channel")

        # self.plt.set_xlim(0, duration)
        self.visualize_wav.pack(side='top', fill=tk.BOTH, expand=1)

    def get_cachefile(self, character, msg):
        _, clean_name = db.clean_customer_name(character.name)
        filename = db.cache_filename(character.name, msg)
        
        return os.path.abspath(
            os.path.join(
                "clip_library",
                character.cat_str(),
                clean_name,
                filename
            )
        )        

    def play_cache(self):
        """
        Play the cachefile
        """
        global ENGINE_OVERRIDE
        message = self.chosen_phrase.get()
        log.debug(f"Speak: {message}")

        # the currently selected character entry on the listside.
        raw_name = self.selected_character.get()
        
        with models.db() as session:
            character = models.get_character_from_rawname(raw_name, session)
       
        if message == self.ALL_PHRASES:
            # we want to re-speak _every_ phrase, one at a time
            message = self.options["values"]
        else:
            message = [ message ]

        for msg in message:
            # skip the all_phrases placeholder if we see it.
            if msg == self.ALL_PHRASES:
                continue
            
            cachefile = self.get_cachefile(character, msg)

            with AudioFile(cachefile) as input:
                # convert the mp3 to a wav
                with AudioFile(
                    filename=cachefile + ".wav",
                    samplerate=input.samplerate,
                    num_channels=input.num_channels,
                ) as output:
                    while input.tell() < input.frames:
                        output.write(input.read(1024))

                self.show_wave(cachefile + ".wav")

                # wrap the wav as an Audio()
                audio = get_audio_from_wav_file(cachefile + ".wav")
                os.unlink(cachefile + ".wav")
                
                # play the Audio()
                voicebox.sinks.SoundDevice().play(audio)            
                        
            
    def say_it(self, use_secondary=False):
        """
        Speak aloud whatever is in the chosen_phrase tk.Variable, using whatever
        TTS engine is selected.
        """
        global ENGINE_OVERRIDE
        message = self.chosen_phrase.get()

        log.debug(f"Speak: {message}")
        # parent is the frame inside DetailSide
        if use_secondary:
            rank = 'secondary'
            engine_name = self.detailside.secondary_tab.selected_engine.get()
        else:
            rank = 'primary'
            engine_name = self.detailside.primary_tab.selected_engine.get()

        ttsengine = engines.get_engine(engine_name)
        log.info(f"Engine: {ttsengine}")

        effect_list = [
            e.get_effect() for e in self.detailside.effect_list.effects
        ]

        # the currently selected character entry on the listside.
        raw_name = self.selected_character.get()
        if not raw_name:
            log.warning('Name is required')
            return
        
        category, name = raw_name.split(maxsplit=1)

        with models.db() as session:
            # it should be get_or_create_character()
            character = models.get_character(name, category, session)

            # every phrase this character has ever said previously.  These make it
            # easy to tune the voice with the same dialog.
            all_phrases = [ 
                n.text for n in session.scalars(
                    select(models.Phrases).where(
                        models.Phrases.character_id == character.id
                    )
                ).all()
            ]

        if message == self.ALL_PHRASES:
            # we want to re-speak _every_ phrase, one at a time to populate the 
            # entire disk cache with the current voice..
            message = self.options["values"]
        else:
            message = [ message ]

        for msg in message:
            # skip the all_phrases placeholder if we see it.
            if msg == self.ALL_PHRASES:
                continue

            _, clean_name = db.clean_customer_name(character.name)
            filename = db.cache_filename(character.name, msg)
            log.debug(f'all_phrases: {all_phrases}')
            if msg in all_phrases:
                cachefile = os.path.abspath(
                    os.path.join(
                        "clip_library",
                        character.cat_str(),
                        clean_name,
                        filename
                    )
                )

                sink = Distributor([
                    SoundDevice(),
                    WaveFile(cachefile + '.wav')
                ])

                log.debug(f'effect_list: {effect_list}')
                log.info(f"Creating ttsengine for {self.selected_character.get()}")

                # None because we aren't attaching any widgets
                try:
                    rank = 'primary'
                    if use_secondary or ENGINE_OVERRIDE.get(character.engine, False):
                        rank = 'secondary'
                    
                    ttsengine(None, rank, self.selected_character).say(msg, effect_list, sink=sink)
                except engines.USE_SECONDARY:
                    ENGINE_OVERRIDE[character.engine] = True
                    return self.say_it(use_secondary=True)
                        
                self.show_wave(cachefile + ".wav")

                log.info('Converting to mp3...')
                with AudioFile(cachefile + ".wav") as input:
                    with AudioFile(
                        filename=cachefile, 
                        samplerate=input.samplerate,
                        num_channels=input.num_channels
                    ) as output:
                        while input.tell() < input.frames:
                            output.write(input.read(1024))
                        log.info(f'Wrote {cachefile}')
                # unlink the wav file?
            else:
                # No Cache
                log.info(f'Bypassing filesystem caching ({msg})')
                try:
                    ttsengine(None, rank, self.selected_character).say(msg, effect_list)
                except engines.DISABLE_ENGINES:
                    # I'm not even sure what we want to do.  The user clicked 'play' but
                    # we don't have any quota left for the selected engine.
                    # lets go dumb-simple.
                    tk.messagebox.showerror(title="Error", message=f"Engine {engine_name} did not provide audio")


class EngineSelection(ttk.Frame):
    """
    Frame for just the Text to speech labal and
    a combobox to choose a different engine.  We are
    tracing on the variable, not binding the widget.
    """

    def __init__(self, parent, selected_engine, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_engine = selected_engine
        ttk.Label(self, text="Text to Speech Engine", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        base_tts = ttk.Combobox(self, textvariable=self.selected_engine)
        base_tts["values"] = [e.cosmetic for e in engines.ENGINE_LIST]
        base_tts["state"] = "readonly"
        base_tts.pack(side="left", fill="x", expand=True)


class EngineSelectAndConfigure(ttk.LabelFrame):
    """
    two element stack, the first has the engine selection,
    the second has all the parameters supported by the seleted engine
    """

    def __init__(self, rank, parent, selected_character, *args, **kwargs):
        kwargs['text'] = 'Engine'
        super().__init__(parent, *args, **kwargs)
        self.rank = rank
        self.selected_character = selected_character

        self.selected_engine = tk.StringVar()
        self.engine_parameters = None
        
        self.selected_engine.trace_add(
            "write", 
            self.change_selected_engine
        )
        with models.Session(models.engine) as session:
            self.load_character(session)

        es = EngineSelection(self, self.selected_engine)
        es.pack(side="top", fill="x", expand=True)

    def set_engine(self, engine_name):
        # this set() will trip change_selected_engine
        # which will in turn set a value for engine_parameters
        self.selected_engine.set(engine_name)  

    def change_selected_engine(self, a, b, c):
        """
        the user changed the engine.
        """
        # No problem.
        # clear the old engine configuration
        # show the selected engine configuration
        log.info('EngineSelectAndConfigure.change_selected_engine()')

        with models.db() as session:
            raw_name = self.selected_character.get()
            character = models.get_character_from_rawname(raw_name, session)
        clear = False

        if self.rank == "primary":
            if character.engine != self.selected_engine.get():
                clear = True
                log.info(f'{self.rank} engine changing from {character.engine!r} to {self.selected_engine.get()!r}')
        elif self.rank == "secondary":
            if character.engine_secondary != self.selected_engine.get():
                clear = True
                log.info(f'{self.rank} engine changing from {character.engine_secondary!r} to {self.selected_engine.get()!r}')

        if self.engine_parameters:
            self.engine_parameters.pack_forget()

        # remove any existing engine level configuration
        if clear:
            with models.db() as session:
                rows = session.scalars(
                    select(models.BaseTTSConfig).where(
                        models.BaseTTSConfig.character_id == character.id,
                        models.BaseTTSConfig.rank == self.rank
                    )
                ).all()

                for row in rows:
                    log.info(f'Deleting {row}...')
                    # if row.key in self.config_vars:
                    #     # remove traces
                    #     info = self.config_vars[row.key].trace_info()
                    #     for i in info:
                    #         self.config_vars[row.key].trace_remove(*i)
                    #     del self.config_vars[row.key]
                    session.delete(row)
                session.commit()

        engine_cls = engines.get_engine(self.selected_engine.get())
        if engine_cls:
            self.engine_parameters = engine_cls(self, self.rank, self.selected_character)
            self.engine_parameters.pack(side="top", fill="x", expand=True)
        else:
            engine_cls = engines.get_engine(settings.DEFAULT_ENGINE)
            self.engine_parameters = engine_cls(self, self.rank, self.selected_character)
            self.engine_parameters.pack(side="top", fill="x", expand=True)

        self.save_character()

    def save_character(self):
        """
        save this engine selection to the database
        """
        log.info('EngineSelectAndConfig.save_character()')
        raw_name = self.selected_character.get()
        if not raw_name:
            log.warning('Name is required to save a character')
            return
        
        category, name = raw_name.split(maxsplit=1)
        engine_string = self.selected_engine.get()
        if engine_string in [None, ""]:
            if category == "player":
                engine_string = settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_PLAYER_ENGINE
                )
            else:
                engine_string = settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                )

        with models.Session(models.engine) as session:
            character = models.get_character(name, category, session)

            log.debug(
                f'''Saving {self.rank} changed engine_string {character.name}
                    {character.engine} {character.engine_secondary} {engine_string}
                ''', 
            )

            if self.rank == "primary" and character.engine != engine_string:
                character.engine = engine_string
            elif self.rank == "secondary" and character.engine_secondary != engine_string:
                character.engine_secondary = engine_string

            session.commit()

    def load_character(self, session):
        """
        We've set the character name, we want the rest of the metadata to
        populate.  Setting the engine name will domino the rest.
        """
        character = models.get_character_from_rawname(
            self.selected_character.get(),
            session=session
        )

        if character is None:
            log.error('Character %s does not exist.' % self.selected_character.get())
            return None
       
        if character.engine in ["", None]:
            if character.category == "player":
                self.selected_engine.set(settings.get_config_key(
                    'DEFAULT_PLAYER_ENGINE', settings.DEFAULT_ENGINE
                ))
            else:
                self.selected_engine.set(settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                ))
        else:
            log.info(f'Setting {self.rank} engine to either ({character.engine} | {character.engine_secondary})')
            if self.rank == "primary":
                self.selected_engine.set(character.engine)
            elif self.rank == "secondary":
                self.selected_engine.set(character.engine_secondary)
            
        return character


class EffectList(ttk.LabelFrame):
    def __init__(self, parent, selected_character, *args, **kwargs):       
        self.selected_character = selected_character
        kwargs['text'] = "Effects",
        super().__init__(parent, *args, **kwargs)

        self.effects = []
        self.buffer = False
        self.load_effects()

        self.add_effect_combo = AddEffect(self, self)
        self.add_effect_combo.pack(side="top", fill="x", expand=True)

    def load_effects(self):
        log.info('EffectList.load_effects()')
        has_effects = False

        # teardown any effects already in place
        while self.effects:
            effect = self.effects.pop()
            effect.clear_traces()
            effect.pack_forget()

        raw_name = self.selected_character.get()
        if raw_name in ["", None]:
            return

        category, name = raw_name.split(maxsplit=1)

        with models.db() as session:
            character = models.get_character(name, category, session)
            
            if character is None:
                log.error(
                    'Cannot load effects.  Character %s|%s does not exist.', 
                    category, name
                )
                return

            voice_effects = session.scalars(
                select(models.Effects).where(
                    models.Effects.character_id==character.id
                )
            ).all()

            for effect in voice_effects:
                has_effects = True
                log.info(f'Adding effect {effect} found in the database')
                effect_class = effects.EFFECTS[effect.effect_name]

                ttk.Style().configure(
                    "Effect.TFrame",
                    highlightbackground="black", 
                )

                # not very DRY
                effect_config_frame = effect_class(
                    self, 
                    borderwidth=1,                     
                    relief="groove",
                    style="Effect.TFrame"
                )
                effect_config_frame.pack(side="top", fill="x", expand=True)
                effect_config_frame.effect_id.set(effect.id)
                self.effects.append(effect_config_frame)

                effect_config_frame.load()
                        
            if not has_effects:
                self.buffer = ttk.Frame(self, width=1, height=1).pack(side="top")
            else:
                if self.buffer:
                    self.buffer.pack_forget()

            log.info("Rebuilding add_effect")
            self.add_effect_combo.pack_forget()
            self.add_effect_combo = AddEffect(self, self)
            self.add_effect_combo.pack(side="top", fill='x', expand=True)
            
    def add_effect(self, effect_name):
        """
        Add the chosen effect to the list of effects the user can manipulate.

        effect name is the nice, button friendly string.  Using it as the
        index for effects.EFFECTS is a bit dirty.  The button should have a
        companion value other than the label, the we can just use that as an
        index.

        This call is for new effects which will start with default configurations.
        """
        effect = effects.EFFECTS[effect_name]
        
        # effect is one of the EffectParameterEditor objects in effects.py
        if effect:
            #
            # effect_config_frame is an instance of one of the
            # EffectParameterEditor objects in effects.py.  They inherit
            # from ttk.Frame. 
            #
            # Instantiating these objects creates any tk objects they need to
            # configure themselves and the ttk.Frame returned can then be
            # pack/grid whatever to arrange the screen.
            # 
            # When we go to render we expect each effect to provide a
            # get_effect(self) that returns an Effect: 
            #   https://github.com/austin-bowen/voicebox/blob/main/src/voicebox/effects/effect.py#L9
            # with an apply(Audio) that returns an Audio; An "Audio" is a pretty
            # simple object wrapping a np.ndarray of [-1 to 1] samples.
            #
            ttk.Style().configure(
                "EffectConfig.TFrame",
                highlightbackground="black", 
                relief="groove"
            )
            effect_config_frame = effect(
                self, 
                style="EffectConfig.TFrame",
                borderwidth=1
            )
            effect_config_frame.pack(side="top", fill="x", expand=True)
            self.effects.append(effect_config_frame)

            raw_name = self.selected_character.get()
            category, name = raw_name.split(maxsplit=1)

            with models.Session(models.engine) as session:
                # retrieve this character
                character = models.get_character(name, category, session)

                # save the current effect selection
                effect = models.Effects(
                    character_id=character.id,
                    effect_name=effect_name
                )
                session.add(effect)
                session.commit()
                session.refresh(effect)

            for key in effect_config_frame.parameters:
                # save the current effect configuration
                tkvar = getattr(effect_config_frame, key)
                value = tkvar.get()

                new_setting = models.EffectSetting(
                    effect_id=effect.id,
                    key=key,
                    value=value
                )
                session.add(new_setting)
            session.commit()
            
            effect_config_frame.effect_id.set(effect.id)      
    
    def remove_effect(self, effect_obj):
        log.info(f'Removing effect {effect_obj}')
        
        # remove it from the effects list
        self.effects.remove(effect_obj)
        effect_id = effect_obj.effect_id.get()
        # remove it from the database
        with models.Session(models.engine) as session:
            # clear any effect settings
            session.execute(
                delete(models.EffectSetting).where(
                    models.EffectSetting.effect_id == effect_id
                )
            )

            # clear the effect itself
            session.execute(
                delete(models.Effects).where(
                    models.Effects.id == effect_id
                )
            )
            session.commit()

        # forget the widgets for this object
        effect_obj.pack_forget()
        self.pack()


class AddEffect(ttk.Frame):
    # where is this 70 coming from?  you got it from where?  what the
    # hell buddy.  This is the shit that causing errors when people
    # use an app at different resolutions.  This will center at one spot
    # and all the other entries will be different.
    add_an_effect = f"{'< Add an Effect >': ^70}"  # pad to center

    def __init__(self, parent, effect_list, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.effect_list = effect_list

        # we're using the textvariable as the action associated with changing
        # this combobox.  That only gives us the scope of what can see this
        # selected_effect to either read the current value or trace_add to 
        # trigger whenever selected_effect is written to.       
        self.selected_effect = tk.StringVar(value=self.add_an_effect)
        self.selected_effect.trace_add("write", self.add_effect)

        effect_combobox = ttk.Combobox(
            self,
            textvariable=self.selected_effect
        )
        #effect_combobox.option_add('*TCombobox*Listbox.Justify', 'center')
        effect_combobox["values"] = list(effects.EFFECTS.keys())
        effect_combobox["state"] = "readonly"

        #  <-[XXX    ]
        effect_combobox.pack(side="left", fill="x", expand=True)

        #  [XXX]->
        # ttk.Button(self, text="Add Effect", command=self.add_effect).pack(side="right")

    def add_effect(self, varname, lindex, operation):
        # Retrieve the currently selected effect from the
        # tk.StringVar.
        effect_name = self.selected_effect.get()
        # effect_list provides a very handy helper to make this easy.  Our
        # output is just providing this effect_list[] for anyone that wants it.
        # Sounds kind of stupid when you actually type it out.
        self.effect_list.add_effect(effect_name)
               
        # reset the UI back to the "add an effect" prompt
        self.selected_effect.set(self.add_an_effect)


class DetailSide(ttk.Frame):
    """
    Primary frame for the "detail" side of the application.
    """
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.selected_character = selected_character
        self.listside = None
        self.trashcan = Feather("trash-2", size=24)

        self.canvas = tk.Canvas(self, borderwidth=0, background="#ffffff")
        self.frame = ttk.Frame(self.canvas)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame_id = self.canvas.create_window(
            (0, 0), window=self.frame, anchor="nw", tags="self.frame"
        )
        self.frame.bind("<Configure>", self.onFrameConfigure)
        # self.frame.pack(side='top', fill='x')

        name_frame = ttk.Frame(self.frame)

        self.character_name = ttk.Label(
            name_frame,
            textvariable=selected_character,
            anchor="center",
            font=font.Font(weight="bold"),
        ).pack(side="left", fill="x", expand=True)

        style = ttk.Style()
        style.configure(
            "RemoveCharacter.TButton",
            width=1
        )

        ttk.Button(
            name_frame,
            image=self.trashcan.icon,
            style="RemoveCharacter.TButton",
            command=self.remove_character
        ).pack(side="right")

        name_frame.pack(side="top", fill="x", expand=True)

        self.group_name = tk.StringVar()
        ttk.Label(
            self.frame,
            textvariable=self.group_name,
            wraplength=220,
            anchor="n",
            justify="center"
        ).pack(side="top", fill="x")

        self.character_description = tk.StringVar()
        ttk.Label(
            self.frame,
            textvariable=self.character_description,
            wraplength=300,
            anchor="nw",
            justify="left"
        ).pack(side="top", fill="x")

        self.phrase_selector = WavfileMajorFrame(
            self.frame, self, selected_character
        )
        self.phrase_selector.pack(side="top", fill="x", expand=True)

        # self.presetSelect = PresetSelector(
        #     self.frame, self, self.selected_character
        # )
        # self.presetSelect.pack(side="top", fill="x", expand=True)

        engine_notebook = ttk.Notebook(self.frame)
        self.primary_tab = EngineSelectAndConfigure(
            'primary', self.frame, self.selected_character
        )
        self.secondary_tab = EngineSelectAndConfigure(
            'secondary', self.frame, self.selected_character
        )
        engine_notebook.add(self.primary_tab, text='Primary')
        engine_notebook.add(self.secondary_tab, text='Secondary')

        engine_notebook.pack(side="top", fill="x", expand=True)

        # list of effects already configured
        self.effect_list = EffectList(self.frame, selected_character)
        self.effect_list.pack(side="top", fill="x", expand=True)

        self.bind('<Enter>', self._bound_to_mousewheel)
        self.bind('<Leave>', self._unbound_to_mousewheel)

    def _bound_to_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def remove_character(self):
        if self.listside:
            self.listside.delete_selected_character()

    def onFrameConfigure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def load_character(self, raw_name):
        """
        load this NPC and populate the detailside widgets
        """
        # set the engine
        # set engine parameters
        # loop effects
        # add each effect
        # set parameters for each effect
        log.info(f'DetailSide.load_character({raw_name})')
        
        # only .set() on selected_character when
        # the value changes so we don't trigger
        # the write callback more often than necessary
        raw_was = self.selected_character.get()
        if raw_was != raw_name:
            self.selected_character.set(raw_name)

        category, name = raw_name.split(maxsplit=1)
        
        if category == "npc":
            npc_data = settings.get_npc_data(name)
            description = ""
            group_name = ""
            if npc_data:
                description = npc_data["description"]
                group_name = npc_data["group_name"]
            self.character_description.set(description)    
            self.group_name.set(group_name)
        else:
            self.character_description.set("")
            self.group_name.set("")

        # load the character 
        with models.db() as session:
            character = models.get_character(name, category, session)

        # update the phrase selector
        self.phrase_selector.populate_phrases()

        # set the engines itself
        log.info('b character: %s | %s | %s', character, character.engine, character.engine_secondary)
        self.primary_tab.set_engine(character.engine)
        self.secondary_tab.set_engine(character.engine_secondary)

        # set engine and parameters
        log.debug(f'{dir(self.primary_tab)=}')
        self.primary_tab.engine_parameters.load_character(raw_name)
        self.secondary_tab.engine_parameters.load_character(raw_name)
        
        # effects
        self.effect_list.load_effects()

        # reset the preset selector
        # self.presetSelect.reset()

        # scroll to the top
        self.vsb.set(0, 1)
        self.canvas.yview_moveto(0)


# class PresetSelector(ttk.Frame):
#     choose_a_preset = f"{'< Use a Preset >': ^70}"

#     def __init__(self, parent, detailside, selected_character, *args, **kwargs):
#         super().__init__(parent, *args, **kwargs)
#         self.selected_character = selected_character
#         self.detailside = detailside
       
#         self.chosen_preset = tk.StringVar(value=self.choose_a_preset)
#         self.chosen_preset.trace_add("write", self.choose_preset)

#         preset_combobox = ttk.Combobox(
#             self,
#             textvariable=self.chosen_preset
#         )
#         preset_combobox["values"] = list(PRESETS.keys())
#         preset_combobox["state"] = "readonly"

#         preset_combobox.pack(side="left", fill="x", expand=True)

#     def reset(self):
#         self.chosen_preset.set(self.choose_a_preset)

#     def choose_preset(self, varname, lindex, operation):
#         log.info('PresetSeelctor.choose_preset()')
#         preset_name = self.chosen_preset.get()
#         if preset_name == self.choose_a_preset:
#             log.info('** No choice detected **')
#             return

#         raw_name = self.selected_character.get()
#         if raw_name:
#             category, name = raw_name.split(maxsplit=1)
#         else:
#             category = 'system'
#             name = None

#         # load the character from the db
#         character = models.get_character(name, category)

#         log.info(f'Applying preset {preset_name}')
#         voice_builder.apply_preset(
#             character.name, 
#             character.category, 
#             preset_name
#         )

#         self.detailside.load_character(self.selected_character.get())


class Character:
    def __init__(self, id, name, engine, category):
        self.id = id
        self.name = name
        self.category = category
    
    @classmethod
    def get_by_raw_name(cls, raw_name):
        if not raw_name:
            return None

        category, name = raw_name.split(maxsplit=1)

        cursor = db.get_cursor()
        character_id, engine_name = cursor.execute(
            "SELECT id, engine FROM character WHERE name = ? AND category = ?", 
            (name, category)
        ).fetchone()
        cursor.close()

        return cls(id=character_id, name=name, engine=engine_name, category=category)

    def __str__(self) -> str:
        return f"{self.category} {self.name}"
    
    def get_phrases(self):
        """
        Return a list of all the phrases this character has previously spoken
        """
        cursor = db.get_cursor()
        phrases = [
            phrase[0] for phrase in cursor.execute("""
                SELECT text FROM phrases WHERE character_id = ?
            """, (self.id, )).fetchall()
        ]
        cursor.close()
        return phrases

class ListSide(ttk.Frame):
    def __init__(self, parent, detailside, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside = detailside
        #wait, what?
        self.detailside.listside = self

        self.list_filter = tk.StringVar(value="")
        listfilter = ttk.Entry(self, width=40, textvariable=self.list_filter)
        listfilter.pack(side="top", fill=tk.X)
        self.list_filter.trace_add('write', self.apply_list_filter)

        self.list_items = tk.Variable(value=[])
        self.refresh_character_list()

        listarea = ttk.Frame(self)
        self.listbox = tk.Listbox(listarea, height=10, listvariable=self.list_items)
        self.listbox.pack(side="left", expand=True, fill=tk.BOTH)
        vsb = tk.Scrollbar(
            listarea,
            orient='vertical',
            command=self.listbox.yview
        )
        self.listbox.configure(yscrollcommand=vsb.set)

        self.bind('<Enter>', self._bound_to_mousewheel)
        self.bind('<Leave>', self._unbound_to_mousewheel)

        vsb.pack(side='right', fill='y')
        listarea.pack(side="top", expand=True, fill=tk.BOTH)

        action_frame = ttk.Frame(self)
        ttk.Button(
            action_frame,
            text="Refresh",
            command=self.refresh_character_list
        ).pack(
            side="right"
        )

        action_frame.pack(side="top", expand=False, fill=tk.X)
        self.listbox.select_set(0)
        self.listbox.bind("<<ListboxSelect>>", self.character_selected)

    def _bound_to_mousewheel(self, event):
        self.listbox.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.listbox.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.listbox.yview_scroll(int(-1*(event.delta/120)), "units")

    def apply_list_filter(self, a, b, c):
        self.refresh_character_list()

    def character_selected(self, event=None):
        if len(self.listbox.curselection()) == 0:
            # we de-selected everything
            # TODO: wipe the detail side?
            return

        index = int(self.listbox.curselection()[0])
        value = self.listbox.get(index)

        self.detailside.load_character(value)

    def refresh_character_list(self):
        log.debug('Refreshing Character list from the database...')

        filter_string = self.list_filter.get()

        with models.db() as session:
            all_characters = session.scalars(
                select(
                    models.Character
                ).order_by(
                    desc(models.Character.last_spoke),
                ).order_by(
                    models.Character.category,
                )
            ).all()

            # yes, this could/should be baked into the query and that would be 
            # more efficient
            if filter_string not in [None, ""]:
                all_characters = [
                    character for character in all_characters if filter_string.upper() in character.name.upper()
                ]

        if all_characters:
            self.list_items.set(
                [f"{character.cat_str()} {character.name}" for character in all_characters]
            )
    
    def delete_selected_character(self):
        index = int(self.listbox.curselection()[0])
        raw_name = self.listbox.get(index)
        log.info(f'Deleting character {raw_name!r}')

        category, name = raw_name.split(maxsplit=1)
        log.info(f'Name: {name!r}  Category: {category!r}')
        
        with models.db() as session:
            character = models.get_character(name, category, session)

            session.execute(
                delete(
                    models.BaseTTSConfig
                ).where(
                    models.BaseTTSConfig.character_id == character.id
                )
            )

            session.execute(
                delete(
                    models.Phrases
                ).where(
                    models.Phrases.character_id == character.id
                )
            )

            all_effects = session.scalars(
                select(
                    models.Effects
                ).where(
                    models.Effects.character_id == character.id
                )
            ).all()
            for effect in all_effects:
                session.execute(
                    delete(
                        models.EffectSetting
                    ).where(
                        models.EffectSetting.effect_id == effect.id
                    )
                )

            session.execute(
                delete(
                    models.Effects
                ).where(
                    models.Effects.character_id == character.id
                )
            )

            try:
                session.execute(
                    delete(models.Character)
                    .where(
                        models.Character.name == name,
                        models.Character.category == models.category_str2int(category)
                    )
                )
                session.commit()

            except Exception as err:
                log.error(f'DB Error: {err}')
                raise

        # TODO: dude, delete everything they have ever said from
        # disk too.

        self.refresh_character_list()
        self.listbox.select_clear(0, 'end')
        self.listbox.select_set(0)
        self.listbox.event_generate("<<ListboxSelect>>")


class ChatterService:
    def start(self, event_queue):
        speaking_queue = queue.Queue()

        npc_chatter.TightTTS(speaking_queue, event_queue)
        speaking_queue.put((None, "Attaching to most recent log...", 'system'))

        logdir = "G:/CoH/homecoming/accounts/VVonder/Logs"
        #logdir = "g:/CoH/homecoming/accounts/VVonder/Logs"
        badges = True
        team = True
        npc = True

        ls = npc_chatter.LogStream(
            logdir, speaking_queue, event_queue, badges, npc, team
        )
        while True:
            ls.tail()


class Chatter(ttk.Frame):
    attach_label = 'Attach to Log'
    detach_label = "Detach from Log"

    def __init__(self, parent, event_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.event_queue = event_queue
        self.button_text = tk.StringVar(value=self.attach_label)
        self.attached = False
        self.hero = None

        settings = models.get_settings()
        
        self.logdir = tk.StringVar(value=settings.logdir)
        self.logdir.trace_add('write', self.save_logdir)

        ttk.Button(
            self, 
            textvariable=self.button_text, 
            command=self.attach_chatter
        ).pack(
            side="left"
        )
        tk.Entry(
            self, 
            textvariable=self.logdir
        ).pack(
            side="left",
            fill='x',
            expand=True
        )
         
        ttk.Button(
            self,
            text="Set Log Dir",
            command=self.ask_directory
        ).pack(side="left")
        
        self.cs = ChatterService()

    def save_logdir(self, *args):
        logdir = self.logdir.get()
        log.info(f'Persisting setting logdir={logdir} to the database...')
        with models.db() as session:
            session.execute(
                update(models.Settings).values(
                    logdir=logdir
                )
            )
            session.commit()

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
            log.info('Detached')
        else:
            # we are not attached, lets do that.
            self.attached = True
            self.button_text.set(self.detach_label)
            self.p = multiprocessing.Process(target=self.cs.start, args=(self.event_queue, ))
            self.p.start()
            log.info('Attached')


# def main():
#     root = tk.Tk()
#     # root.iconbitmap("myIcon.ico")
#     root.geometry("640x480+200+200")
#     root.resizable(True, True)
#     root.title("Character Voice Editor")

#     chatter = Chatter(root, None)
#     chatter.pack(side="top", fill="x")

#     editor = ttk.Frame(root)
#     editor.pack(side="top", fill="both", expand=True)

#     cursor = db.get_cursor()
    
#     first_character = cursor.execute("select id, name, category from character order by name").fetchone()
    
#     cursor.close()

#     if first_character:
#         selected_character = tk.StringVar(value=f"{first_character[2]} {first_character[1]}")
#     else:
#         selected_character = tk.StringVar()

#     detailside = DetailSide(editor, selected_character)
#     listside = ListSide(editor, detailside)

#     listside.pack(side="left", fill="x", expand=True)
#     detailside.pack(side="left", fill="x", expand=True)

#     root.mainloop()


# if __name__ == '__main__':
#     if sys.platform.startswith('win'):
#         multiprocessing.freeze_support()
#     main()

