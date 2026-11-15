@echo off
setlocal
REM Requires: Git, Rust (rustup), Python 3.10+ (all on PATH)
if not exist engine (
  git clone --depth 1 https://github.com/shibahex/asset-replacer-roblox.git engine || goto :fail
)
pushd engine
cargo build --release || (popd & goto :fail)
popd
python -m pip install --upgrade pyinstaller -r requirements.txt || goto :fail
python -m PyInstaller --noconfirm --onefile --windowed --name AssetReplacer --collect-data sv_ttk ^
  --add-binary "engine\target\release\animation-replace-roblox.exe;." app.py || goto :fail
echo.
echo Done: dist\AssetReplacer.exe
exit /b 0
:fail
echo Build failed.
exit /b 1
