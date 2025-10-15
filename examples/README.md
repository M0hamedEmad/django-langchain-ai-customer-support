# Examples (demo only, not part of the product)

## Streamlit demo client

```bash
# Terminal 1: API (from repo root)
python manage.py runserver

# Terminal 2: demo UI
streamlit run examples/streamlit_demo.py
```

The demo logs in with phone number + company API key (default `gym_2` for local
seed data) and talks to `http://localhost:8000/api/v1/chat/stream`.
