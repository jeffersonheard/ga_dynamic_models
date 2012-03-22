from celery.task import task
import subprocess

@task
def restart_ga():
    """This is hideous. Make ga_dynamic_models work without restarting the server"""
    subprocess.call("sleep 2 && supervisorctl restart ga", shell=True)