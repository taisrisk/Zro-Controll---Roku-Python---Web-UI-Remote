# ZroControl (Local Roku Control Dashboard)

## Run

```powershell
cd roku_dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` and use **LAN** to discover/select a Roku.

## Notes

- Uses Roku ECP over HTTP (`:8060`) and SSDP discovery (`ST: roku:ecp`).
- Active device IP is stored in your browser (`localStorage`) for easy tab switching.

