# SimScan

**An offline auditor for The Sims 4 Mods folder.** Point it at your Mods
folder; it tells you what is broken, what is duplicated, what is fighting,
and — crucially — what the game is *silently ignoring*.

Nothing is uploaded. No account. No internet connection required.
The source is free and MIT-licensed; the built Windows binaries are US$14.

---

## Why this exists

The Sims 4 gives you a folder and no tools. Existing managers are good at
browsing and organising, and there are trackers for "is this mod updated
yet", but four things routinely go wrong and almost nothing catches them:

| Problem | What usually happens | What SimScan does |
|---|---|---|
| **Script mods that never load** | You tidy your folder, bury a `.ts4script` two levels deep, and it stops working. No error, no `LastException`, no clue. | Flags every `.ts4script` below the depth the game actually reads |
| **Duplicates under different names** | You re-download `Hair.package` and get `Hair (1).package`. Name-based duplicate checkers miss it entirely. | Compares **content hashes**, so identical files are caught whatever they are called |
| **Conflicts with an unknown winner** | Two mods change the same thing. Most tools say "these conflict"; none say which one the game actually applies. | Works out the winner from `Resource.cfg` priority, folder depth and filename order, and names it |
| **Corrupt packages** | One damaged download can make a folder look broken. | Reads every package's resource index and reports what will not parse |

It also reads the game's own crash reports and ranks your installed mods by
how likely each one explains the crash, then writes you a 50/50 test plan.

## What it does *not* do

Being straight with you, because this area is full of tools that over-promise:

- **It cannot prove which mod caused a crash.** Nothing can, except the game
  reproducing the fault. SimScan ranks suspects; you still have to test them.
- **It cannot do 50/50 testing for you.** It writes the plan and halves the
  work; it will not launch your game.
- **It is not antivirus.** For script-mod malware, use ModGuard.
- **It is not a mod manager.** It does not download or update mods. Use a
  mod manager for that.

## Install

Download `SimScan-1.0.2-Setup.exe` and run it. Windows will show a
SmartScreen warning because the installer is not code-signed — click
**More info → Run anyway**. You get a Start Menu entry and a normal
uninstaller.

There is also a portable build: unzip and run `SimScan.exe`.

## Using it

1. Launch SimScan. It finds your Mods folder automatically in most cases.
   Otherwise click **Browse…**.
2. It scans. A large folder (50,000 files) takes a few minutes the first
   time; it is hashing every file.
3. Read the **Findings** tab. Each finding says what is wrong, what the
   evidence is, and what to do.
4. Actions are safe by default:
   - **Disable selected** moves files into a `_disabled` folder inside Mods
     (the game ignores folders starting with `_`). Nothing is deleted, and
     **Undo last change** puts them back.
   - **Delete…** sends files to the Recycle Bin, not oblivion.
5. **Export report…** writes an HTML/CSV/JSON/TXT report — handy when asking
   for help on a forum.

### The tabs

- **Findings** — everything wrong, worst first, with the exact files.
- **Load order** — the order the game will actually load your packages in,
  which is what decides who wins a conflict.
- **All files** — every file with its size, type, resource count and, where
  the package records one, the creator name and the mod's real title. Click
  a row to see a thumbnail pulled straight out of the package.
- **Last exception** — read the game's crash reports and rank suspects.

## Command line

Useful for scripting or a big folder you want to report on:

```bat
SimScan.exe --cli "C:\Users\you\Documents\Electronic Arts\The Sims 4\Mods"
SimScan.exe --cli --html report.html --csv files.csv
SimScan.exe --cli --exception 0          :: newest crash report
```

Exit code is `1` when high-severity findings exist, `0` otherwise.

## How it works

`.package` files are DBPF 2.1 archives. SimScan parses the resource index
directly, decompresses each resource (stored, zlib or EA RefPack) and
compares the resulting `type:group:instance` keys between packages. Two
packages defining the same key with different content are a conflict.

Mod names come from the package's string tables (STBL v5, UTF-8) and its
tuning XML. Artwork is decoded from the game's DDS textures, which use
Sims-specific FOURCC codes (`DST1`/`DST3`/`DST5`) that map onto the standard
DXT1/DXT3/DXT5 block formats — Pillow rejects them, so SimScan decodes them
itself.

## Building from source

```bash
pip install pillow pyinstaller
pyinstaller --clean --noconfirm build/simscan.spec   # -> dist/SimScan/
iscc build/simscan.iss                               # -> dist/installer/
```

Run from source without building:

```bash
python -m simscan              # GUI
python -m simscan.cli FOLDER   # command line
```

Requires Python 3.9+ and tkinter.

## See it

SimScan has a page of its own now, showing the report the app actually
produces from a deliberately broken folder:

<https://caseone115.github.io/simscan/>

## Buy it

SimScan is a paid download (US$14) at https://teeterbot.gumroad.com/l/simscan.
The source stays MIT and public here: read it, build it, or audit it before you
ever pay for anything. Buying gets you the acceptance-tested Windows build,
both the installer and the portable zip, so you do not have to construct it
yourself.

## Acceptance testing status

The **portable** build has been run as the shipped Windows executable: pointed
at a deliberately broken Mods folder it reported the planted defects (dead
script mod, duplicate files under different names, resource conflict, empty
package, files that should not be in Mods) and wrote a parseable report.

The **installer** is now proven end to end on real Windows. Its GitHub Actions
build (`.github/workflows/build-windows.yml`, runs on `windows-latest`) installs
it silently, asserts the installed `SimScan.exe`, the uninstaller and the Start
Menu shortcut exist, then runs the *installed* copy against the same kind of
broken folder and requires exit code 1 with all three planted defects present.
It then uninstalls silently and asserts nothing was left behind.

The checksums of the two shipped files are published next to the same two files,
cut from the build that ran the test above, so the hashes and the binaries always
come from one build: they are attached to the latest GitHub Release and to the
paid listing itself.

The source suite is 48 checks locally, of which 47 run on Windows against Python
3.9 and 3.12 by the same workflow.

## Licence

MIT. See `LICENSE`.
