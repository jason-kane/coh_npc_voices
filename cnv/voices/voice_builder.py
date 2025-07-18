import logging
import os
import re

import pyfiglet
from sqlalchemy import select
from voicebox.sinks import Distributor, WaveFile

import cnv.database.models as models
import cnv.lib.settings as settings
from cnv.effects.base import registry as effect_registry
from cnv.engines.base import registry as engine_registry
from cnv.engines.base import USE_SECONDARY



log = logging.getLogger(__name__)

PLAYER_CATEGORY = models.category_str2int("player")

# I'm actually a little curious to see exactly how this will behave.  From npcChatter this is being called in
# a subprocess, but when the editor triggers it we are in a thread.  The thread dies, the new thread doesn't know
# ENGINE_OVERRIDE has been triggered and we keep smacking elevenlabs even though we've run out of credits.

ENGINE_OVERRIDE = {}


def create(character, message, session):
    """
    This NPC exists in our database but we don't
    have this particular message rendered.

    This is how npc_chatter talks.  editor has its own seperate-but=equal
    version of this, they should really be merged. (WIP)

    1. Get vocal characteristics from sqlite using 
       the npc_id
    2. Render message based on that data
    3. persist as an mp3 in cachefile
    """
    global ENGINE_OVERRIDE
    log.debug(f'voice_builder.create({character=}, {message=})')
    
    voice_effects = session.scalars(
        select(models.Effects).where(
            models.Effects.character_id == character.id
        )
    ).all()
    
    effect_list = []
    for effect in voice_effects:
        log.debug(f'Adding effect {effect} found in the database')
        effect_class = effect_registry.get_effect(effect.effect_name)
        effect_instance = effect_class(None)

        effect_instance.effect_id.set(effect.id)
        effect_instance.load()  # load the DB config for this effect

        effect_list.append(effect_instance.get_effect())

    rank = 'primary'
    if ENGINE_OVERRIDE.get(character.engine, False):
        rank = 'secondary'

    # have we seen this particular phrase before?
    #if character.category != PLAYER_CATEGORY or settings.get_toggle(settings.taggify("Persist player chat")):
        # phrase_id = models.get_or_create_phrase_id(
        #     name=character.name,
        #     category=character.category,
        #     message=message
        # )
        
    # message = models.get_translated(phrase_id)


    try:
        clean_name = re.sub(r'[^\w]', '',character.name)
        os.mkdir(os.path.join(settings.clip_library_dir(), character.cat_str(), clean_name))
    except OSError:
        # the directory already exists.  This is not a problem.
        pass

    #     save = True
    # else:
    #     # play it without saving it.
    #     # sink = Distributor([
    #     #     SimpleAudioDevice()
    #     # ])
    #     save = False 
    
    name = character.name
    category = character.category
    
    # character.engine may already have a value.  It probably does.  We're over-writing it
    # with anything we have in the dict ENGINE_OVERRIDE.  But if we don't have anything, you can keep
    # your previous value and carry on.

    try:
        if rank == 'secondary':
            raise USE_SECONDARY
        
        cachefile = settings.get_cachefile(
            character.name, 
            message, 
            character.cat_str(),
            rank
        )

        #if save:
        sink = Distributor([
            #SimpleAudioDevice(),
            WaveFile(cachefile + '.wav')
        ])
        # else:
        #     sink = Distributor([
        #         SimpleAudioDevice()
        #     ])

        log.debug(f'Using engine: {character.engine}')
        
        # every character gets a primary engine config, even if it's os TTS.
        engine = engine_registry.get_engine(character.engine)

        #TTSEngine.__init__(self, parent, rank, name, category, *args, **kwargs):
        engine(
            None, 
            'primary', 
            name, 
            category
        ).say(
            message, 
            effect_list, 
            sink=sink
        )

    except USE_SECONDARY:
        rank = 'secondary'
        # our chosen engine for this character isn't working.  So we're going to switch
        # to the secondary and use that for the rest of this session.
        ENGINE_OVERRIDE[character.engine] = True
        log.debug("\n" + pyfiglet.figlet_format(
                "Engaging\nSecondary\nEngine", 
                font="3d_diagonal", width=120
            )
        )
        
        # new rank, new cachefile
        cachefile = settings.get_cachefile(
            character.name, 
            message, 
            character.cat_str(),
            rank
        )

        # new cachefile, new sink.
        #if save:
        sink = Distributor([
            #SimpleAudioDevice(),
            WaveFile(cachefile + '.wav')
        ])
        # else:
        #     sink = Distributor([
        #         SimpleAudioDevice()
        #     ])

        if character.engine_secondary:
            # use the secondary engine config defined for this character
            engine_instance = get_engine(character.engine_secondary)
            engine_instance(None, 'secondary', name, category).say(message, effect_list, sink=sink)
        else:
            # use the global default secondary engine
            engine_name = settings.get_config_key(f"{character.category}_engine_secondary")
            engine_instance = get_engine(engine_name)
            engine_instance(None, 'secondary', name, category).say(message, effect_list, sink=sink)
     
        # End result: cachefile + ".wav" exists, for at least one of primary/secondary.

