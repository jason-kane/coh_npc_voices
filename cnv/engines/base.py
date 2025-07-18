import logging
import tkinter as tk
from typing import Type

import customtkinter as ctk
import voicebox
from markdown_it import MarkdownIt
from sqlalchemy import select
from tkinterweb import HtmlLabel

import cnv.database.models as models
import cnv.lib.settings as settings

log = logging.getLogger(__name__)


class USE_SECONDARY(Exception):
    """
    signal to disable this engine for this session
    """

class MarkdownLabel(HtmlLabel):  # Label
    def __init__(self, *args, **kwargs):
        md = MarkdownIt(
            'commonmark',
            {
                'breaks': True,
                'html': True
            }
        )
        #  
        text = f"""<body style="background-color:#CCC">
        {md.render(kwargs.pop('text'))}
        </body>"""
        
        kwargs['text'] = text
        super().__init__(*args, **kwargs)


# Base Class for TTS engines/services
class TTSEngine(ctk.CTkFrame):
    auth_ui_class = None
    cosmetic="TTSEngine Base Class (You screwed up buddy)"

    def __init__(self, parent, rank, name, category, *args, **kwargs):
        log.debug(f'Initializing TTSEngine {parent=} {rank=} {name=} {category=}')
        super().__init__(parent, *args, **kwargs)

        self.rank = rank
        self.name = name
        self.category = category
        self.override = {}
        self.parameters = set('voice_name')
        self.config_vars = {}
        self.widget = {}

        self.set_config_meta(self.config)
        self.draw_config_meta()

        self.load_character(category=category, name=name)
        self.repopulate_options()

    def get_config_meta(self):
        with models.db() as session:
            response = session.scalars(
                select(models.EngineConfigMeta).where(
                    models.EngineConfigMeta.engine_key == self.key
                )
            ).all()
        return response

    def set_config_meta(self, *rows):
        # wipe existing configuration metadata
        with models.db() as session:
            old_settings = session.scalars(
                select(models.EngineConfigMeta).where(
                    models.EngineConfigMeta.engine_key==self.key
                )
            ).all()

            for old_row in old_settings:
                session.delete(old_row)
            session.commit()

        with models.db() as session:
            for row in rows[0]:
                # log.info(f"{row=}")
                cosmetic, key, varfunc, default, cfg, fn = row
                field = models.EngineConfigMeta(
                    engine_key=self.key,
                    cosmetic=cosmetic,
                    key=key,
                    varfunc=varfunc,
                    default=default,
                    cfgdict=cfg,
                    gatherfunc=fn
                )
                session.add(field)
            session.commit()

    def say(self, message, effects, sink=None, *args, **kwargs):
        tts = self.get_tts()
        # log.info(f'{self}.say({message=}, {effects=}, {sink=}, {args=}, {kwargs=}')
        log.debug(f'Invoking voicebox.SimpleVoicebox({tts=}, {effects=}, {sink=})')
        vb = voicebox.SimpleVoicebox(
            tts=tts,
            effects=effects, 
            sink=sink
        )

        if message:

            try:
                vb.say(message)
                log.debug('vb.say(message) complete')
            except Exception as err:
                log.error('vb: %s', vb)
                log.error("Error in TTSEngine.say(): %s", err)
                if hasattr(err, "grpc_status_code"):
                    # google error
                    #  Error in TTSEngine.say(): 503 failed to connect to all addresses; last error: UNAVAILABLE: ipv4:172.217.12.106:443: WSA Error
                    
                    # this is what happens when you try to use google TTS when
                    # networking is borked.
                    log.error(err)
                    if err.grpc_status_code == 14:
                        log.error(f'Google Error code {err.grpc_status_code}.  Switching to secondary.')
                        raise USE_SECONDARY

                elif err.status_code == 401:
                    log.error(err.body)
                    if err.body.get('detail', {}).get('status') == "quota_exceeded":
                        log.error('ElevelLabs quota exceeded.  Switching to secondary.')
                        raise USE_SECONDARY
                raise

    def get_tts(self):
        return voicebox.tts.tts.TTS()

    def load_character(self, category, name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        # settings.how_did_i_get_here()
        if name is None:
            return

        self.loading = True
        self.name = name
        self.category = category
        
        with models.db() as session:
            character = models.Character.get(name, category, session)

        self.gender = settings.get_npc_gender(character.name)
        
        engine_config = models.get_engine_config(character.id, self.rank)

        for key, value in engine_config.items():
            log.debug(f'Setting config {key} to {value}')
            
            # log.info(f"{dir(self)}")
            if hasattr(self, 'config_vars'):
                # the polly way
                log.debug(f'PolyConfig[{key}] = {value}')
                # log.info(f'{self.config_vars=}')
                if key in self.config_vars:
                    self.config_vars[key].set(value)
            else:
                log.error(f'OBSOLETE config[{key}] = {value}')
                # everything else
                getattr(self, key).set(value)
                setattr(self, key + "_base", value)

        # log.info("TTSEngine.load_character complete")
        self.loading = False
        return character

    def save_character(self, name, category):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        # log.info(f"save_character({name}, {category})")

        character = models.Character.get(name, category)

        if character is None:
            # new character?  This is not typical.
            # log.info(f'Creating new character {name}`')
            
            with models.db() as session:
                character = models.Character(
                    name=name,
                    category=models.category_str2int(category),
                    engine=settings.get_config_key(
                        'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                    ),
                )
            
                session.add(character)
                session.commit()
                session.refresh(character)

            # log.info("character: %s", character)
            for key in self.parameters:
                # log.info(f"Processing attribute {key}...")
                # do we already have a value for this key?
                value = str(getattr(self, key).get())

                # do we already have a value for this key?
                with models.db() as session:
                    config_setting = session.execute(
                        select(models.BaseTTSConfig).where(
                            models.BaseTTSConfig.character_id == character.id,
                            models.BaseTTSConfig.rank == self.rank,
                            models.BaseTTSConfig.key == key,
                        )
                    ).scalar_one_or_none()

                    if config_setting and config_setting.value != value:
                        log.debug('Updating existing setting')
                        config_setting.value = value
                        session.commit()

                    elif not config_setting:
                        log.debug('Saving new BaseTTSConfig')
                        with models.db() as session:
                            new_config_setting = models.BaseTTSConfig(
                                character_id=character.id, 
                                rank=self.rank,
                                key=key, 
                                value=value
                            )
                            session.add(new_config_setting)
                            session.commit()

    def draw_config_meta(self):
        # now we build it.  Row 0 is taken by the engine selector, the rest is ours.
        # column sizing is handled upstream, we need to stay clean 
        self.columnconfigure(0, minsize=125, weight=0, uniform="ttsengine")
        self.columnconfigure(1, weight=2, uniform="ttsengine")

        for index, m in enumerate(self.get_config_meta()):
            ctk.CTkLabel(self, text=m.cosmetic, anchor="e").grid(
                row=index + 1, column=0, sticky="e", padx=10
            )

            # create the tk.var for the value of this widget
            varfunc = getattr(tk, m.varfunc)
            log.debug(f'Stashing {varfunc} in config_vars[{m.key}]')
            
            if m.key in self.config_vars:
                for trace in self.config_vars[m.key].trace_info():
                    log.debug('Removing duplicate trace...')
                    self.config_vars[m.key].trace_remove(trace[0], trace[1])

            self.config_vars[m.key] = varfunc()
            self.config_vars[m.key].set(m.default)

            # create the widget itself
            if m.varfunc == "StringVar":
                self._tkStringVar(index + 1, m.key, self)
            elif m.varfunc == "DoubleVar":
                self._tkDoubleVar(index + 1, m.key, self, m.cfgdict)
                self.config_vars[m.key].trace_add("write", self.reconfig)
            elif m.varfunc == "BooleanVar":
                self._tkBooleanVar(index + 1, m.key, self)
                self.config_vars[m.key].trace_add("write", self.reconfig)
            else:
                # this will fail, but at least it will fail with a log message.
                log.error(f'No widget defined for variables like {varfunc}')

            # changes to the value of this widget trip a generic 'reconfig'
            # handler.

    def _tkStringVar(self, index, key, frame):
        # combo widget for strings
        self.widget[key] = ctk.CTkComboBox(
            frame,
            variable=self.config_vars[key],
            command=self.reconfig,
            state="readonly"
        )
        # self.widget[key]["state"] = "readonly"
        self.widget[key].grid(row=index, column=1, columnspan=2, sticky="new")

    def _tkDoubleVar(self, index, key, frame, cfg):
        # doubles get a scale widget.  I haven't been able to get the ttk.Scale
        # widget to behave itself.  I like the visual a bit better, but its hard
        # to get equivilent results.


        # TODO:
        # display the current value
        # mark ticks/steps?
        # use digits/resolution to determine steps?
        #
        if cfg.get('resolution'):
            steps = int((cfg['max'] - cfg.get('min', 0)) / cfg.get('resolution'))
        else:
            steps = 20
        
        if steps > 50:
            log.warning(f'Resolution for {key} is too detailed')

        self.widget[key] = ctk.CTkSlider(
            frame,
            variable=self.config_vars[key],
            from_=cfg.get('min', 0),
            to=cfg['max'],
            orientation='horizontal',
            number_of_steps=steps
        )            
        self.widget[key].grid(row=index, column=1, sticky="new")

        ctk.CTkLabel(
            frame,
            textvariable=self.config_vars[key]
        ).grid(row=index, column=2, sticky='e')

    def _tkBooleanVar(self, index, key, frame):
        """
        Still using a label then checkbutton because the 'text' field on
        checkbutton puts the text after the button.  Well, and it will make it
        easier to maintain consistency with the other widgets.  Oh, and text
        doesn't belong on a checkbox.  It's a wart, sorry.
        """
        self.widget[key] = ctk.CTkSwitch(
            frame,
            text="",
            variable=self.config_vars[key],
            onvalue=True,
            offvalue=False
        )
        self.widget[key].grid(row=index, column=1, sticky="new")

    def reconfig(self, *args, **kwargs):
        """
        Any engine value has been changed.  In most cases this is a single
        change, but it could also be multiple changes.  The changes are between
        the current values in all the UI configuration widgets and the values
        stored in the database.

        We need to persist the changes, but in some cases changes can cascade.
        For example changing the language can change the available voices.  So
        each time a change comes through we shake the knob to see if any of our
        combo widgets need to repopulate.
        """
        if self.loading:
            log.debug('Voice config change while loading... (ignoring)')
            return
        
        log.debug(f'reconfig({args=}, {kwargs=})')
        with models.db() as session:
            character = models.Character.get(
                name=self.name, 
                category=self.category,
                session=session
            )
    
        config = {}
        for m in self.get_config_meta():
            config[m.key] = self.config_vars[m.key].get()
        
        log.debug(f'GUI config values are: {config}')
        
        models.set_engine_config(character.id, self.rank, config)
        self.repopulate_options()

    def repopulate_options(self):
        for m in self.get_config_meta():
            # for cosmetic, key, varfunc, default, cfg, fn in self.CONFIG_TUPLE:
            # our change may filter the other widgets, possibly
            # rendering the previous value invalid.
            if m.varfunc == "StringVar":
                # log.info(f"{m.cosmetic=} {m.key=} {m.default=}
                # {m.gatherfunc=}") m.gatherfunc() is the function on the module
                # responsible for returning all configuration options available
                # in this plugin.
                all_options = getattr(self, m.gatherfunc)()
                if not all_options:
                    log.error(f'{m.gatherfunc=} returned no options ({self.cosmetic})')

                if m.key in self.widget:
                    # log.info(f'{all_options=}')
                    self.widget[m.key].configure(values=all_options)

                    if all_options:
                        if self.config_vars[m.key].get() not in all_options:
                            # log.info(f'Expected to find {self.config_vars[m.key].get()!r} in list {all_options!r}')                    
                            self.config_vars[m.key].set(all_options[0])
            
    def _gender_filter(self, voice):
        if hasattr(self, 'gender') and self.gender:
            # log.debug(f'{self.gender.title()} ?= {voice["gender"].title()}')
            try:
                return self.gender.title() == voice["gender"].title()
            except KeyError:
                log.warning('Failed to find "gender" in:')
                log.debug(f"{voice=}")
        return True


class UnknownEngine(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

        log.error("Unknown engine: %s", args)
        #log.error(f"{self.engines=}")
        #log.error(f"{self.engines_by_cosmetic=}")


class EngineRegistry:
    """
    engines in this registry are expected to be subclasses of TTSEngine.
    """
    def __init__(self):
        self.engines = {}
        self.engines_by_cosmetic = {}

    def add_engine(self, cls):
        key = cls.key
        self.engines[key] = cls
        self.engines_by_cosmetic[cls.cosmetic] = cls
    
    def get_engine(self, key) -> Type[TTSEngine]:
        if key in self.engines:
            return self.engines[key]
        
        if key in self.engines_by_cosmetic:
            return self.engines_by_cosmetic[key]
        
        raise UnknownEngine(key)
    
    def engine_list(self) -> list:
        out = []
        for engine in self.engines:
            out.append((engine, self.engines[engine]))
        return out
    
    def count(self):
        return len(self.engines)
    
registry = EngineRegistry()