# Asset Replacer GUI
Desktop front end for [shibahex/asset-replacer-roblox](https://github.com/shibahex/asset-replacer-roblox).
Fields: cookie, API key (Assets read+write), place file, output, group, thread count, asset-type filter, dry run.

## Get the .exe
**Option A (local, Windows):** install Git, Rust (rustup), Python 3.10+, then run `build.bat` -> `dist\AssetReplacer.exe`.
**Option B (no installs):** push this folder to a GitHub repo, open Actions -> "Build exe" -> Run workflow, download the `AssetReplacer` artifact.

Cookie and API key are kept in memory only, are masked in the log, and are passed to the engine as CLI flags (so they are visible to local process viewers while it runs).

## Credits
Built on [shibahex/asset-replacer-roblox](https://github.com/shibahex/asset-replacer-roblox) (MIT). Always credit the original animators of any assets you reupload.
