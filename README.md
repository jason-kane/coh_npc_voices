# What is this?

This program started as a fairly simplistic python program that watches the City of Heroes chat log file.  When it sees a message from an NPC, it uses the windows text-to-speech capability to read out the message.  It also notices when you receive a badge and tells you which badge you got.

It still does that, mostly.  Instead of using the same built-in voice for everything, it uses different voices now.  It supports a bunch of voice effects.  Adding new effects is pretty easy.  

When Sidekick starts you get a GUI.  It shows every character you've seen and allows you to modify the voice profile for each of them.

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/4c9f2372-ce67-43f3-b13a-c822d1b4a952)

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

Paid text-to-speech services are supported.  Right now that includes both google text-to-speech and ElevenLabs.  For google you'll need a valid application default login.  https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login  I know it is a pain.  The quality and flexibility are much better than windows defaults but it takes a moment to generate.  Responses are cached to keep costs down to near zero.

ElevenLabs voices support is just barely getting started.  To use it you will need to place a text file named "eleven_labs.key" containing only your API key in the main sidekick directory.

Voice effects can be configured and layered with some fun results.  For better or worse, the UI for manipulating this is immediate --  Whenever you change something it is automatically saved and if you are in-game you will start to hear the new voice.

The voices used by default are the free Windows TTS API voices.  It isn't great.  Install more windows voices first.

Players on your team get voices too.  Find them in the list to modify what they sound like.  When players talk it is NOT cached.

Overall I think this companion program makes City of Heroes much more immersive.  I can't wait to record a video showing it off, maybe a shorter taskforce like Yin?

# Installation

Go to the releases page:

    https://github.com/jason-kane/coh_npc_voices/releases

Download sidekick_setup.exe and run it.  Windows will not want to do it since I'm not paying 300/year for an application certificate.

# Configuration

You will need to use "Set Log Dir" in the upper right corner and point it at your City of Heroes log directory.

It will vary based on the installer.  Probably something like:

    <COH Install Directory>/accounts/<Account Name>/logs/
    <COH Install Directory>/homecoming/accounts/<Account Name>/Logs/

You will need to enable logging on your character inside the game.

You can use this slash command in the chat window:

    /logchat

The first time you'll need to quite to char selection, and choose the same character again.  Now you're ready to "Attach to Log".

# Usage

The "Character" tab currently shows a graph of how much XP/minute your character earned in the last hour of playtime.  The samples are binned into one minute intervals and the graph updates once per minute.

Any NPC that talks will get a voice.  If you don't like the way it sounds you can use the "Voices" tab, find the character that spoke and fiddle with it.  You'll find a record of the things that NPC says in the dropdown so you can tune it based on their own words.  It all saves itself as you go.

You can choose a "Preset" for any character.  These change the initial voice settings to make it easy for all the characters in a given group (like Vahzilok) to all sound similar.  The "Random" options are nice when you don't really care that much but want some quick variety.


# Manual Installation

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Upgrade

    pip install --upgrade git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Uninstall

    pip uninstall coh_npc_voices

# Adding Voices (Highly Recommended)

Making new free voices available is an easy way to increase the variety and flavor of voices you hear in the city.

## Windows 10

Open Settings, choose Time & Language
Choose Speech on the left side
Choose "Add voices" under Manage voices

By itselt that will probably only give you one or two more voices, even if you install a dozen.  There is a powershell script 'enable_all_win10_voices.ps' that copies voices from the "only use for windows transcribe" part of the registry out to the "use for anything" part.

You probably have to logout/login before the extra voices are available.

# Running it (Manual Install)

Start a cmd terminal and run:

    sidekick.exe

Start City of Heroes; any host.  login and pick any character.  Then enable chat logging.

You can use this slash command in the chat window:

    /logchat

It is also in the settings UI somewhere.

This is a per-character thing so if you aren't getting voices double check this first.

Next you will need to figure out where your logs are stored.  It will vary based on the installer.

    <COH Install Directory>/accounts/<Account Name>/logs/
    <COH Install Directory>/homecoming/accounts/<Account Name>/Logs/

Use "Set Log Dir" in the upper right corner to configure it for your log location.  You should only need to do this once.  It is a little trixy because it needs to see the "Welcome to Paragon City" thing in the log.  That means you probably have to enable logging, then logout/login, _then_ "Attach to Log".  It's annoying, but it only happens the first time.

Once you are ready You will need to click "Attach to Log" in the upper left corner after you are in-game.  The "Attach" button changes to a "Detach".  You can attach/detach whenever you want.

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

# Building the Windows Installer

First run fresh.bat

    fresh.bat

That will clean-slate the venv directory and apply some path detection tweaks.  Next run innosetup, load this projects .iss file then -> Build -> Compile.  Build -> Open Output folder will give you the dir with the sidekick_setup.exe.

The way this works is a little bit awesome.  sidekick_setup.exe will install our files and a barebones python venv, then it will run win_install, which is a compiled version of win_install.ps1.  It installs (w/pip) all our dependencies.  End result?  A small (5MB) setup executable that installs all the crap we need (I'm looking at you numpy.  Try eating a salad).  Running it again?  No problem.  If you use the same destination directory it won't even need to re-download the packages.  The best part from my POV is the actual running code is sitting there for the user to poke at with no obfuscation.

I'm currently pleased as punch with the installer.  Kind of hell to get it all figured out but the results are quite nice.

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

Raw entity data from https://cod.uberguy.net/html/index.html
