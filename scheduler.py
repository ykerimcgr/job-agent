import time
from datetime import datetime, time as dt_time

from main import run_pipeline_once


START_TIME = dt_time(9, 0)
END_TIME = dt_time(17, 0)
INTERVAL_MINUTES = 60


def is_active_time():
    now = datetime.now().time()
    return START_TIME <= now < END_TIME


def run_scheduler():
    print("Job agent scheduler started ✔")

    while True:
        now = datetime.now()

        if is_active_time():
            print(f"\n[{now}] Running job pipeline...")

            try:
                run_pipeline_once(send_email=True)
            except Exception as e:
                print(f"Pipeline error: {e}")

            print(f"Sleeping for {INTERVAL_MINUTES} minutes...")
            time.sleep(INTERVAL_MINUTES * 60)

        else:
            print(f"[{now}] Outside active hours. Exiting scheduler.")
            break


if __name__ == "__main__":
    run_scheduler()