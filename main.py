"""h2ox-forecast - run daily"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

from flask import Flask, request
from loguru import logger

from h2ox.forecast import download_tigge, ingest_local_grib
from h2ox.forecast.slackbot import SlackMessenger
from h2ox.forecast.utils import create_task, deploy_task, upload_blob

app = Flask(__name__)


if __name__ != "__main__":
    # Redirect Flask logs to Gunicorn logs
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    app.logger.info("Service started...")
else:
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


def format_stacktrace():
    parts = ["Traceback (most recent call last):\n"]
    parts.extend(traceback.format_stack(limit=25)[:-2])
    parts.extend(traceback.format_exception(*sys.exc_info())[1:])
    return "".join(parts)


@app.route("/", methods=["POST"])
def run_daily():

    """Receive a request and queue downloading ecmwf data

    Request params:
    ---------------

        today: str


    # download forecast (tigge or HRES)
    # ingest to zarr

    #if pubsub:
    envelope = request.get_json()
    if not envelope:
        msg = "no Pub/Sub message received"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        msg = "invalid Pub/Sub message format"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    request_json = envelope["message"]["data"]

    if not isinstance(request_json, dict):
        json_data = base64.b64decode(request_json).decode("utf-8")
        request_json = json.loads(json_data)

    logger.info('request_json: '+json.dumps(request_json))

    # parse request
    today_str = request_json['today']

    """

    time.time()

    payload = request.get_json()

    if not payload:
        msg = "no message received"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    logger.info("payload: " + json.dumps(payload))
    logger.info("environ")
    logger.info(f"{os.environ.keys()}")

    if not isinstance(payload, dict):
        msg = "invalid task format"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    token = os.environ.get("SLACKBOT_TOKEN")
    target = os.environ.get("SLACKBOT_TARGET")

    if target is not None and token is not None:

        slackmessenger = SlackMessenger(
            token=token,
            target=target,
            name="w2w-forecast",
        )
    else:
        slackmessenger = None

    today_str = payload["today"]
    forecast = payload["forecast"]

    today = datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=None)

    if forecast == "tigge":
        # do tigge stuff
        do_tigge(today, slackmessenger)

        return f"Ran day {today.isoformat()[0:10]}", 200

    elif forecast == "hres":
        # do hres stuff

        raise NotImplementedError


def do_tigge(today, slackmessenger):

    tigge_store_path = os.environ.get("TIGGE_STORE_PATH")
    tigge_zarr_path = os.environ.get("TIGGE_ZARR_PATH")
    tigge_timedelta_days = int(os.environ.get("TIGGE_TIMEDELTA_DAYS"))
    token_path = os.environ.get("TIGGE_TOKEN_PATH")
    email = os.environ.get("TIGGE_EMAIL")
    key = os.environ.get("TIGGE_KEY")
    ecmwf_url = os.environ.get("ECMWF_URL")
    n_workers = int(os.environ.get("N_WORKERS"))
    zero_dt = datetime.strptime(os.environ.get("TIGGE_ZERO_DT"), "%Y-%m-%d")
    requeue = str(os.environ.get("REQUEUE")).lower() == "true"

    # 1. download tigge
    logger.info("downloading tigge")
    fpath = download_tigge(today, tigge_timedelta_days, email, key, ecmwf_url)
    if slackmessenger is not None:
        slackmessenger.message(
            f"TIGGE ::: downloaded {today.isoformat()[0:10]}-{(today+timedelta(days=tigge_timedelta_days)).isoformat()[0:10]}"
        )
    # 2. push .grib to storage
    remote_path = os.path.join(tigge_store_path, os.path.split(fpath)[-1])
    logger.info(f"storing tigge {fpath} to {tigge_store_path}")
    upload_blob(fpath, remote_path)

    # 3. ingest .grib
    logger.info(f"ingesting tigge {fpath} to {tigge_zarr_path}")
    ingest_local_grib(fpath, tigge_zarr_path, n_workers, zero_dt)
    logger.info(f"done ingesting tigge {fpath} to {tigge_zarr_path}")

    # 4. push a token to storage
    local_token_path = os.path.join(os.getcwd(), "token.json")
    token = {"most_recent_tigge": (today + timedelta(hours=24)).isoformat()[0:10]}
    json.dump(token, open(local_token_path, "w"))
    upload_blob(local_token_path, token_path)

    # 4. enque tomorrow's grib
    if requeue:
        enqueue_tomorrow(today, "tigge")
    if slackmessenger is not None:
        slackmessenger.message(
            f"TIGGE ::: Done, enqueued {(today+timedelta(days=tigge_timedelta_days)).isoformat()}"
        )

    return 1


def enqueue_tomorrow(today, forecast):

    tomorrow = today + timedelta(hours=48)  # every two days

    cfg = dict(
        project=os.environ.get("project"),
        queue=os.environ.get("queue"),  # queue name
        location=os.environ.get("location"),  # queue
        url=os.environ.get("url"),  # service url
        service_account=os.environ.get("service_account"),  # service acct
    )

    task = create_task(
        cfg=cfg,
        payload=dict(today=tomorrow.isoformat()[0:10], forecast=forecast),
        task_name=tomorrow.isoformat()[0:10] + f"-{forecast}",
        delay=48 * 3600,
    )

    deploy_task(cfg, task)

    return 1
