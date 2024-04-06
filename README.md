# What is this?

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/4c9f2372-ce67-43f3-b13a-c822d1b4a952)

This is kinda two programs joined at the hip.  I intend to integrate them a bit better at some point.  Right now, it provides an interface for modifying the voices of characters, both NPC and player in City of Heroes.  If you provide it with the path to your game chat logs (and enable chat logs) then "Attach to Log", it will learn the names of characters that speak and remember what they say.  It will also pass that text to the default Windows TTS voice.  You'll "hear" what enemies and team members say.  Not only that, but if you choose to, you can change what the characters voices sound like.

There are two kinds of change available right now.  The biggest difference comes from changing the TTS source from Windoes TTS to Google TTS (ElevenLabs and Parrot soon).  That requires a google cloud account with billing attached.  For something like this, it's pennies cheap.  Good for some variety for humans, but sometimes you need more.

So we have audio effects.  Currently these filters:
    Bandpass Filter
    Bandstop Filter
    Bitcrush
    Chorus
    Clipping
    Compressor
    Glitch
    Highpass Filter
    Lowpass Filter
    Normalize
    RingMod
    Vocoder

can be configured and layered with some fun results.  For better or worse, the UI for manipulating this is immediate --  Whenever you change something it is automatically saved and if you are in-game you will start to hear the new voice.

Overall I think this companion program makes City of Heroes a little more immersive.

# Installation

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Upgrade

    pip install --upgrade git+https://github.com/jason-kane/coh_npc_voices.git

# Uninstall

    pip uninstall coh_npc_voices

# Adding Voices (Worth a shot)

Making new free voices available is an easy way to increase the variety and flavor of voices you hear in the city.

## Windows 10

Open Settings, choose Time & Language
Choose Speech on the left side
Choose "Add voices" under Manage voices

It won't list everything you install and I don't know why.  If you figure out how to get them all recognized let me know.

# Running it

Start a cmd terminal and run:

    coh_voices.exe

Start City of Heroes; any host.  login and pick any character.  Then enable chat logging.

You can use this slash command in the chat window:

    /logchat

It is also in the settings UI somewhere.

This is a per-character thing so if you aren't getting voices double check this first.

Next you will need to figure out where your logs are stored.  It will vary based on the installer.

    <COH Install Directory>/accounts/<Account Name>/logs/
    <COH Install Directory>/homecoming/accounts/<Account Name>/Logs/

The right directory will have files with names like "chatlog 2024-03-31.txt".  If you are having trouble turn on /logchat for a few minutes in-game, then look for file named after todays date.

Use "Set Log Dir" in the upper right corner to configure it for your log location.  You should only need to do this once.

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/73c1b2de-04ed-4096-bf10-b1baaa19d152)

Once you are ready You will need to click "Attach to Log" in the upper left corner after you are in-game.  The "Attach" button changes to a "Detach".  You can attach/detach whenever you want.


# Local Development

If you are curious and want to poke around at the source code it is right here.  You can download your own copy with "git".

    git clone https://github.com/jason-kane/coh_npc_voices.git
    cd coh_npc_voices

The python source is in src/coh_npc_voices.  I've only made minimal efforts to make it nice.  It is tied to tkinter more than I would like.  The blend of multiprocess and threads is confusing; and core functionality is replicated for no good reason.

But it does work, and it is fun.

# Preloaded Data

This is a tricky one.  I've only really been gathering processed audio for a little while.  I doubt the 161 characters I have represent more than a 5% of the game dialog and I'm at 61MB.  Each phrase is cached as a 100KB-ish mp3.  You can edit/delete them however you want.  If a cachefile exists it will be played instead of generating new audio.  I do like the idea of sharing the database with all the characters audio configs, especially if users can easily choose to share what they create.  I'm just not sure how best to go about it.  TBD.  I'll at least share my database as the default setup but tweaked to use free voices when it has enough customization to be worthwhile.

# Problems?

Please leave an issue here in github.  I can't promise anything but I'm very likely to read it.

# License?

MIT.  I think that means you are allowed to do what you want, just don't blame me if it all goes wrong.  That said I would appreciate pull requests if you make improvements so we can share the benefits.


# Dependencies

In many ways this is a UI wrapper around a mashup of these three modules:

https://github.com/austin-bowen/voicebox/
https://github.com/DeepHorizons/tts
https://github.com/spotify/pedalboard

Big thanks and shoutout for the creators of these packages.
