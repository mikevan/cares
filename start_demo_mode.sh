python clear_database.py    # Drops all tables, recreates structure
python load_sample_data.py  # Loads fresh sample data
exec gunicorn app:app
