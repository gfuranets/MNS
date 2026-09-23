## MNS - Medical Notification System


## 1. 














## Launching server and app
1. Create local instance of MySQL databse
```bash
sudo mysql < query.sql
source venv/bin/activate
cd app/
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
