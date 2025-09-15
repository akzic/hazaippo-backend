# app/tasks/tasks.py
from celery import shared_task

@shared_task(name='app.tasks.tasks.process_image_ai')
def process_image_ai(image_path, latitude=0, longitude=1, preprocess=False):
    if preprocess:
        print("Preprocessing enabled.")
    else:
        print("No preprocessing.")

    return {"status": "success"}
