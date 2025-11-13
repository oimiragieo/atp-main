# Dev tasks

- Set environment and run the aggregator:

```powershell
$env:ROUTERS = "http://localhost:8000"; $env:ADMIN_API_KEY = "<admin-key>"; python -m uvicorn admin_aggregator.app:app --reload --port 8081
```
