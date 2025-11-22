# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cnv\\sidekick.py'],
    pathex=['.', 'cnv'],
    binaries=[
        (
            '.venv\\Lib\\site-packages\\azure\\cognitiveservices\\speech\\Microsoft.CognitiveServices.Speech.core.dll', 
            '.'
        ),
        ('.venv\\Lib\\site-packages\\pyfiglet', '.\\pyfiglet'),
        ('sidekick.ico', '.'),
        ('cnv\\lib\\icons\\trash-2.png', 'cnv\\lib\\icons\\'),
        ('all_npcs.json', '.'),
    ],
    datas=[
        ('cnv\\effects\\*', 'cnv\\effects\\'),
        ('cnv', 'cnv'),
        ('.venv\\Lib\\site-packages\\better_profanity\\alphabetic_unicode.json', 'better_profanity\\'),
        ('.venv\\Lib\\site-packages\\better_profanity\\profanity_wordlist.txt', 'better_profanity\\'), 
    ],
    # dependencies of engines, we have to do this out here because I made them runtime modules inside.
    hiddenimports=[
        'pyfiglet',
        'pyfiglet.fonts',
        'boto3',  # amazon
        'google_auth_oauthlib',  # google
        'openai',  # umm?  (joking, duhh)
        'comtypes',  # windows tts
        'azure',
        'azure.cognitiveservices',
        'azure.cognitiveservices.speech',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='sidekick',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='sidekick',
)
