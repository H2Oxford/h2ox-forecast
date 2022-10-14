# Use the baseline ubuntu image
FROM osgeo/gdal:ubuntu-small-latest

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True


# Set default env vars to clear CI
#ENV PROVIDER GCP

ENV APP_HOME /app

COPY ./main.py $APP_HOME/
COPY ./batch.py $APP_HOME/

# Copy local code to the container image.
# __context__ to __workdir__
COPY . h2ox-forecast

# Install apt dependencies
RUN apt-get update
RUN apt-get install -y python3-pip
RUN apt-get install -y libeccodes0

RUN echo $PWD

RUN echo $(ls)


RUN pip install h2ox-forecast/

WORKDIR $APP_HOME

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
#CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
CMD python batch.py
