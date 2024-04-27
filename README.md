# What is this?

This program started as a fairly simplistic python program that watches the City of Heroes chat log file.  When it sees a message from an NPC, it uses the windows text-to-speech capability to read out the message.  It also notices when you receive a badge and tells you which badge you got.

It still does that, mostly.  Instead of using the same built-in voice for everything, it uses different voices now.  It supports a bunch of voice effects.  Adding new effects is pretty easy.  

When Sidekick starts you get a text window and a GUI.  It takes a hot second to get going.

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/cd233679-b559-4633-9fe2-785e9d640c3a)

After you've started the game and are logged in with your character (and have followed the steps under 'Configure' to enable loggin) click "Attach to Log" and you'll see something more like this:

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/d749697e-05f8-41bc-8142-22576ed54d12)

As you play that will expand out to graph of your experience gained over time.  Its a good way to gauge your progress in the game.

You'll also start hearing things.  This time the voices in your head are real.  Whenever an NPC or a team member says something in chat, it will be converted into audio.

Don't like what someone sounds like?  That is what the "Voices" tab is for:

![image](https://github.com/jason-kane/coh_npc_voices/assets/1907832/17e2d134-a6df-49de-9c9c-b1af4544a85f)


## More/Better Voices (Highly Recommended)

Adding more voices is an easy way to increase the variety and flavor of sounds you hear in the city.

### Local Windows TTS Voices

#### Windows 10

1. Open Settings, choose Time & Language
2. Choose Speech on the left side
3. Choose "Add voices" under Manage voices

By itselt that will probably only give you one or two more voices, even if you install a dozen.  There is a powershell script 'enable_all_win10_voices.ps' that copies voices from the "only use for windows transcribe" part of the registry out to the "use for anything" part.

You probably have to logout/login before the extra voices are available.

### Google Text-to-Speech

Paid text-to-speech services are supported.  Right now that includes both google text-to-speech and ElevenLabs.  For google you will need a valid application default login.  https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login  I know it is a pain.  The quality and flexibility are much better than windows defaults but it takes a moment to generate.  Responses are cached to keep costs down to near zero.

### ElevenLabs

ElevenLabs voices support is just barely getting started.  To use it you will need to place a text file named "eleven_labs.key" containing only your API key in the main sidekick directory.

# Voice Effects

We have a lot of audio effects.  Currently:
* Bandpass Filter
* Bandstop Filter
* Bitcrush
* Chorus
* Clipping
* Compressor
* Glitch
* Highpass Filter
* Lowpass Filter
* Normalize
* RingMod
* Vocoder

Voice effects can be configured and layered with some fun results.  For better or worse, the UI for manipulating this is immediate --  Whenever you change something it is automatically saved and if you are in-game you will start to hear the new voice for anything that isn't cached.  You can choose the bottom option in the phrases dropdown to 
"Rebuild all phrases".  It will... rebuild all the phrases.

The voices used by default are the free Windows TTS API voices.  It isn't great.  Install more windows voices first.  Instructions below.

Players on your team get voices too.  Find them in the list to modify what they sound like.  When players talk it is NOT cached, that tickled by privacy bone and the value of the cache is minimal.

# Installation

Go to the releases page:

    https://github.com/jason-kane/coh_npc_voices/releases

Download sidekick_setup.exe and run it.  Windows will not want to do it since I'm not paying 300/year for an application certificate.  The setup program is small (5MB-ish) but this thing downloads some heavy packages like numpy.  Just a heads up in case your connection is slow or expensive.

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

# OSX / Linux?

90% of this is totally compatible, no problem.  The other 10% is the windows sapi stuff; making it platform detect and default to the (good) osx text-to-voice or the (not as good) linux espeak will take some effort but isn't particularly difficult.

# Manual Installation

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Upgrade

    pip install --upgrade git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Uninstall

    pip uninstall coh_npc_voices


# Manual Installation

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Upgrade

    pip install --upgrade git+https://github.com/jason-kane/coh_npc_voices.git

# Manual Uninstall

    pip uninstall coh_npc_voices

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

To restore the dev environment after cutting a release, run
    dirty.bat

# Problems?

Please leave an issue here in github.  I can't promise anything but I'm very likely to read it.

# License?

MIT.  I think that means you are allowed to do what you want, just don't blame me if it all goes wrong.  That said I would appreciate pull requests if you make improvements so we can all share the benefits.

# Dependencies

In many ways this is a UI wrapper around a mashup of these three modules:

https://github.com/austin-bowen/voicebox/
https://github.com/DeepHorizons/tts
https://github.com/spotify/pedalboard

Big thanks and shoutout for the creators of these packages.

Raw entity data from https://cod.uberguy.net/html/index.html
