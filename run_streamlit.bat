@echo off
title Meesho AI Video Director - Streamlit Dashboard
cd /d %~dp0
echo ========================================================
echo   MEESHO AI VIDEO DIRECTOR - STREAMLIT DASHBOARD
echo   Local URL:    http://localhost:8501
echo   Network URL:  http://10.254.159.37:8501
echo ========================================================
python -m streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
pause
