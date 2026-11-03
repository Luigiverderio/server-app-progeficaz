"""Execução no Linux/EC2: gunicorn --config gunicorn.conf.py app:app."""

# O limitador do Nominatim é local ao processo: mantenha apenas um worker.
workers = 1
worker_class = "gthread"
threads = 4
bind = "127.0.0.1:5000"
timeout = 60
accesslog = "-"
errorlog = "-"
