[<img alt="Wave2Web Hack" width="1000px" src="https://github.com/H2Oxford/.github/raw/main/profile/img/wave2web-banner.png" />](https://www.wricitiesindia.org/content/wave2web-hack)

H2Ox is a team of Oxford University PhD students and researchers who won first prize in the[Wave2Web Hackathon](https://www.wricitiesindia.org/content/wave2web-hack), September 2021, organised by the World Resources Institute and sponsored by Microsoft and Blackrock. In the Wave2Web hackathon, teams competed to predict reservoir levels in four reservoirs in the Kaveri basin West of Bangaluru: Kabini, Krishnaraja Sagar, Harangi, and Hemavathy. H2Ox used sequence-to-sequence models with meterological and forecast forcing data to predict reservoir levels up to 90 days in the future.

The H2Ox dashboard can be found at [https://h2ox.org](https://h2ox.org). The data API can be accessed at [https://api.h2ox.org](https://api.h2ox.org/docs#/). All code and repos can be [https://github.com/H2Oxford](https://github.com/H2Oxford). Our Prototype Submission Slides are [here](https://docs.google.com/presentation/d/1J_lmFu8TTejnipl-l8bXUZdKioVseRB4tTzqK6sEokI/edit?usp=sharing). The H2Ox team is [Lucas Kruitwagen](https://github.com/Lkruitwagen), [Chris Arderne](https://github.com/carderne), [Tommy Lees](https://github.com/tommylees112), and [Lisa Thalheimer](https://github.com/geoliz).

# H2Ox - Forecast
This repo is for a dockerised service to ingest [ECMWF](https://www.ecmwf.int/) [TIGGE](https://www.ecmwf.int/en/research/projects/tigge) data into a [Zarr archive](https://zarr.readthedocs.io/en/stable/). The Zarr data is rechunked in the time domain in blocks of four years. This ensures efficient access to moderately-sized chunks of data, facilitating timeseries research. Two variables are ingested: two-meter temperature (t2m) and total precipitation (tp). TIGGE data is acquired in the `.grib` [format](https://github.com/ecmwf/cfgrib) which requires [special binaries](https://packages.ubuntu.com/bionic/libs/libeccodes0) to be open and read.

## Installation

This repo can be `pip` installed:

    pip install https://github.com/H2Oxford/h2ox-forecast.git

For development, the repo can be pip installed with the `-e` flag and `[dev]` options:

    git clone https://github.com/H2Oxford/h2ox-forecast.git
    cd h2ox-forecast
    pip install -e .[dev]

For containerised deployment, a docker container can be built from this repo:

    docker build -t <my-tag> .

Cloudbuild container registery services can also be targeted at forks of this repository.

## Useage

### Credentials

ECMWF serves TIGGE data using the [ecmwf-api-client](https://github.com/ecmwf/ecmwf-api-client) library.
Access to the TIGGE data requires an ECMWF account and api key.
Follow the [instructions here](https://www.ecmwf.int/en/computing/software/ecmwf-web-api) for access.
Once logged in, API key details can be found here: https://api.ecmwf.int/v1/key/, and saved at `~/.ecmwfapirc`.
These fields will be needed for setting environment variables.

A slackbot messenger is also implemented to post updates to a slack workspace.
Follow [these](https://api.slack.com/bot-users) instuctions to set up a slackbot user, and then set the `SLACKBOT_TOKEN` and `SLACKBOT_TARGET` environment variables.

### Ingestion

The Flask app in `main.py` listens for a POST http request and then triggers the ingestion workflow.
The http request must have a json payload with a YYYY-mm-dd datetime string keyed to "today": `{"today":"<YYYY-mm-dd>"}`.
The ingestion script then:

1. enqueues and downloads the TIGGE forecast data from the ECMWF API
2. pushed the downloaded `.grib` file to cloud storage
3. ingests the `.grib` file into the zarr archive
4. pushes a completion token to cloud storage to track progress
5. enqueues tomorrows ingestion task in the cloud task queue


The following environment variables are required:

    SLACKBOT_TOKEN=<my-slackbot-token>                # a token for a slack-bot messenger
    SLACKBOT_TARGET=<my-slackbot-target>              # target channel to issue ingestion updates
    TIGGE_STORE_PATH=<gs://path/to/tigge/grib/files>  # the path to the raw .grib files for ingestion
    TIGGE_ZARR_PATH=<gs://path/to/tigge/zarr/archive> # the path to the tigge zarr archive
    TIGGE_TIMEDELTA_DAYS=<int>                        # the frequency with which to request new TIGGE data, e.g. every <2> days
    TIGGE_TOKEN_PATH=<gs://path/to/tigge/token.json>  # the directory to store the tigge ingestion token
    TIGGE_EMAIL=<your@email.com>                      # the email address associated with your ecmwf account
    TIGGE_KEY=<api-key>                               # the api key associated with your ecwmf account
    ECMWF_URL=<http://ecwmf/api/endpoint>             # the ecwmf api endpoint url
    n_workers=<int>                                   # the number of workers to ingest with
    zero_dt=<YYYY-mm-dd>                              # the initial date of the zarr archive for indexing

To requeue the next day's ingestion, the ingestion script will push a task to a [cloud task queue](https://cloud.google.com/tasks/docs/creating-queues) to enqueue ingestion for tomorrow. This way a continuous service is created that runs daily. The additional environment variables will be required:

    project=<my-gcp-project>            # gcp project associated with queue and cloud storage
    queue=<my-queue-name>               # queue name where pending tasks can be places
    location=<my-queue-region>          # location name for task queue
    url=<http://my/dockerised/service>  # url of the entrypoint for the docker container to be run
    service_account=<myacct@email.com>  # service account for submitting tasks and http request


Environment variables can be put in a `.env` file and passed to the docker container at runtime:

    docker run --env-file=.env -t <my-tag>

### Accessing ingested data

[xarray](https://docs.xarray.dev/en/stable/) can be used with a zarr backend to lazily access very large zarr archives.

<img alt="Zarr Xarray" width="600px" src="https://github.com/H2Oxford/.github/raw/main/profile/img/zarr_tigge.png"/>


## Citation

TIGGE can be cited as:

    Swinbank, R., Kyouda, M., Buchanan, P., Froude, L., Hamill, T. M., Hewson, T. D., Keller, J. H., Matsueda, M., Methven, J., Pappenberger, F., Scheuerer, M., Titley, H. A., Wilson, L., & Yamaguchi, M. (2016). The TIGGE Project and Its Achievements, Bulletin of the American Meteorological Society, 97(1), 49-67. https://journals.ametsoc.org/view/journals/bams/97/1/bams-d-13-00191.1.xml

Our Wave2Web submission can be cited as:

    <citation here>
