@echo off
cd /d "C:\Users\bhara\OneDrive\Desktop\Trading"

REM Add GitHub remote (replace bajju08 with your username)
git remote add origin https://github.com/bajju08/dma-car-swing-trading.git

REM Commit all files
git add .
git commit -m "Initial commit - Complete DMA-DMA+CAR swing trading platform"

REM Push to GitHub
git branch -M main
git push -u origin main

pause
