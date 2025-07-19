# Sidekick Installation

From a fresh, clean windows 10 installation -- which isn't what anyone has, but it is a good baseline.  And I'm lying to you, I don't really have a clean windows 10.  I have a fresh vmware workstation windows 10, with vmware tools installed.

First you need to download the sidekick.zip from github.

  https://github.com/jason-kane/coh_npc_voices/releases

As I'm writing this the most recent version is v4.1.1

124MB later, and I open the .zip file.  Sorry it's such a bloated pig.  The way to make it smaller is to remove the numpy dependency.  That would cut 2/3rds of it.  Numpy is good at doing math fast.  I'm using it to convert mp3 to wav files -- some of the text-to-speech services deliver mp3 files.  It's also used for some of the voice effects, most critically the vocoder I'm using to make the clockwork sound robotic.

The contents of the zip file are "clip_library" and "sidekick".  I'm just going to drag them both to my desktop.  You can put them anywhere, just remember where you put them.

Open up the sidekick folder.

<img width="809" height="162" alt="image" src="https://github.com/user-attachments/assets/94987072-cbf3-4f8e-b02c-391cc2f1593d" />

You should see "_internal" and "sidekick".  Feel free to browse around _internal if you are interested.  It has all the python modules used by sidekick.  The python code for sidekick itself is in there too if you are curious.  It's under "cnv".

Enough mucking around, back to the top of the sidekick folder.  Open "sidekick"

Microsoft Defender SmartScreen may pop in with a "hey buddy, this is some risky shit, you sure this is what you want?"  I'm paraphrasing, but longer.  Ultraphrasing?

"More info", then "Run Anyway" because we are brave heroes.

Black console window pops up, a bunch of words fly past, then you see the user interface (UI).

<img width="722" height="672" alt="image" src="https://github.com/user-attachments/assets/6ac8e8e9-a100-44d8-98ee-cfea0c5f376e" />

## Initial Configuration

### Paths

Go to the "Configuration" tab.  The two two buttons are critical.  The first is "COH Log Dir".  Click the button, find your City of Heroes log directory.  The exact location depends on how you installed City of Heroes.

<img width="722" height="672" alt="image" src="https://github.com/user-attachments/assets/74610524-3392-4efd-8a0f-b2be92fe1f8f" />

In my case it is: `C:/coh/homecoming/accounts/VVonder/Logs` 

The second one is "Set Clip Library Dir".  Click that, and find the clip_library directory.  You don't have to use the one included in the .zip but you certainly can.  An empty directory is also fine.  This is where the .wav files for everything you hear in the game are stored to be re-used.

### Primary/Secondary Engines

You will also need to chose the primary and secondary TTS engine for each of "npc", "player", and "system".

This might seem a bit weird.  The intention is to make it easy to spread the requests across multiple services.  This keeps your usage within the generous free-tier for the services.  Sidekick tries to nicely failover from Primary to Secondary when the Primary free tier is exhausted.

For the purposes of this tutorial/test, I am choosing "Windows TTS" for everything.

In the middle are four checkboxes.  "Acknowledge each win", "Persist player chat", "Speak Buffs" and "Speak Debuffs".  I like it chatty, so I'm turning them all on.

<img width="679" height="214" alt="image" src="https://github.com/user-attachments/assets/05a5f1a5-28fe-4bf1-b3ff-ffb284a93ca0" />

To use better services you would add appropriate credentials on the bottom of the configuration tab.  There is a sub-tab sort of thing for each supported service with some documentation about how to get your own credentials.

Setting one or more of these up is optional but recommended.

<img width="719" height="330" alt="image" src="https://github.com/user-attachments/assets/f006df39-a739-420e-82af-22777685b81f" />

That is it.  You don't need to save or anything.  It saves changes as you make them.

### Does it work?

You can test the TTS on the "Voices" tab.  There is a placeholder "default" entry.

Which I just tried, and it failed.  With a clean Windows 10 install there aren't any Windows TTS voices.  "Voice Name" is "<unconfigured>".

### Voices 

So lets install some voices.  Search down by the start menu for "Speech" and open "Speech settings"

<img width="781" height="641" alt="image" src="https://github.com/user-attachments/assets/ec6e0b4a-d772-42ad-a3b6-a96c77cd0bed" />

under "Manage voices" click "Add voices", add all the "English" voices.  Australia, Canada, India, Ireland, UK.  All of em'
Wait for the bars to fill.. it takes ridiculously longer than it should for 150-ish MB of voice files.

<img width="1043" height="836" alt="image" src="https://github.com/user-attachments/assets/416f326a-ceee-45a6-b96e-d1352ce1c8b5" />

Hang in there, now we want to start powershell.  Search for "powershell", "Run as Administrator".  Running random powershell scripts as administrator is a lovely way to blow off your foot, so take a second to understand what this does before you run it. 

<img width="784" height="640" alt="image" src="https://github.com/user-attachments/assets/7ba34e37-697a-4479-844d-227d389b2d32" />

You are going to run these commands in the blue powershell window:

```
$sourcePath = 'HKLM:\software\Microsoft\Speech_OneCore\Voices\Tokens' # Where the OneCore voices live
$destinationPath = 'HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens' # For 64-bit apps
$destinationPath2 = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\SPEECH\Voices\Tokens' # For 32-bit apps

cd $destinationPath

$listVoices = Get-ChildItem $sourcePath

foreach($voice in $listVoices)
{
  $source = $voice.PSPath #Get the path of this voices key
  copy -Path $source -Destination $destinationPath -Recurse
  copy -Path $source -Destination $destinationPath2 -Recurse
}
```
What that does is copy the voice tokens from the OneCore location to the standard Speech location, making all the installed voices available for all applications.  Like sidekick.

You can verify that it worked by running
```
dir HKLM:\SOFTWARE\Microsoft\Speech\Voices\Tokens
```
It should have a bunch of entries instead of just the default three.

Start sidekick again.  Go to "Voices".  The "Voice Name" dropdown should have multiple options and you should be able to click "Regen" and hear whatever has been typed into the box next to it.

<img width="722" height="672" alt="image" src="https://github.com/user-attachments/assets/4332e913-df1d-4f3c-b0ac-4af81e1ce16f" />

## Back to the Game
And.. City of Heroes?

Smartass.  You are going to want to start the game, login, choose your character and enter the game.

_After_ you are inside the game, go to the Sidekick window (control-escape to get out of coh), then go to the "Character" tab.

<img width="722" height="672" alt="image" src="https://github.com/user-attachments/assets/2f4d8ecf-1e34-4222-831f-afca0254fdd4" />

Click "Attach to Log"

Then within 10 seconds return to the game.

If you have the log path configured correctly you are done.  You should hear a welcome message and any chatter from NPCs should be voiced.  If you join a team whatever your team members say is voiced.  Etc., Etc.

Welcome to the good life.

