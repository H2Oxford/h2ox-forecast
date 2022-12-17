import multiprocessing as mp
import os
from datetime import timedelta
from multiprocessing.shared_memory import SharedMemory

import dask.array
import gcsfs
import numpy as np
import pandas as pd
import xarray as xr
import zarr
from ecmwfapi import ECMWFDataServer
from loguru import logger


def download_tigge(start_dt, end_dt, email, key, ecmwf_url):

    server = ECMWFDataServer(email=email, key=key, url=ecmwf_url)

    fname = os.path.join(
        os.getcwd(), f"{start_dt.isoformat()[0:10]}_{end_dt.isoformat()[0:10]}.grib"
    )

    server.retrieve(
        {
            "class": "ti",
            "dataset": "tigge",
            "date": f"{start_dt.year}-{start_dt.month:02d}-{start_dt.day:02d}/to/{end_dt.year}-{end_dt.month:02d}-{end_dt.day:02d}",
            "expver": "prod",
            "grid": "0.5/0.5",
            "levtype": "sfc",
            "origin": "ecmf",
            "param": "167/228228",
            "step": "0/6/12/18/24/30/36/42/48/54/60/66/72/78/84/90/96/102/108/114/120/126/132/138/144/150/156/162/168/174/180/186/192/198/204/210/216/222/228/234/240/246/252/258/264/270/276/282/288/294/300/306/312/318/324/330/336/342/348/354/360",
            "time": "00:00:00",
            "type": "cf",
            "target": fname,
        }
    )

    return fname


def ingest_local_grib(grib_path, gcs_root, n_workers, zero_dt):

    logger.info(f"ingesting {grib_path} to {gcs_root}")

    pool = mp.Pool(n_workers)
    logger.info("loading and chunking data")

    ds_dask = xr.open_dataset(
        grib_path,
        chunks={"longitude": 10, "latitude": 10, "steps": 61, "time": 1461},
        engine="cfgrib",
    )
    ds = xr.open_dataset(grib_path, engine="cfgrib")

    start_dt = pd.to_datetime(ds["time"].min().values).to_pydatetime()
    
    time_offset = int((start_dt - zero_dt).days)
    
    # load the slices
    slices = dask.array.core.slices_from_chunks(
        dask.array.empty_like(ds_dask.to_array()).chunks
    )  # null, time, lat, lon

    # eliminate the slices which hit the boundary and only the first variable
    slices = [s for s in slices if s[3].stop != 361 and s[0].start == 0]

    for variable in ds.data_vars.keys():

        logger.info(f"ingesting variable {variable}")

        data = ds[variable].values

        # transpose to correct shape
        data = np.transpose(data, [3, 2, 0, 1])
        
        if n_workers>1:
            # do multiprocessing

            logger.info(f"assigning to sharedemem: {data.nbytes}")
            # create the shared memory space
            shm = SharedMemory(create=True, size=data.nbytes)

            # create the shared array
            logger.info('Create shared array')
            data_shm = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)

            # write the data into shared mem
            data_shm[:] = data[:]

            shm_spec = {"name": shm.name, "shape": data.shape, "dtype": data.dtype}

            logger.info(f"Got {len(slices)} slices")
            # prep for multiprocessing
            chunk_worker = len(slices) // n_workers + 1
            slices_rechunked = [
                slices[chunk_worker * ii : chunk_worker * (ii + 1)]
                for ii in range(n_workers)
            ]

            args = [
                (shm_spec, variable, gcs_root, slices_rechunked[ii], time_offset, ii)
                for ii in range(n_workers)
            ]

            logger.info("Calling MP Pool with sharedmem")
            # single threaded first
            # for arg in args:
            #    sharedmem_worker(*arg)

            pool.starmap(sharedmem_worker, args)

            del data_shm  # Unnecessary; merely emphasizing the array is no longer used
            shm.close()
            shm.unlink()  # Free and release the shared memory block at the very end
            
        else:
            
            # open the zarr
            store = gcsfs.GCSMap(root=gcs_root)
            z = zarr.open(store)

            # write each slice
            for ii_s, s in enumerate(slices):
                if ii_s % 100 == 0:
                    logger.info(f"single_worker, ii_s:{ii_s}")

                time_slice = s[1]
                offset_slice = slice(s[1].start + time_offset, s[1].stop + time_offset)
                step_slice = s[2]
                lat_slice = s[3]
                lon_slice = s[4]
                z[variable][lon_slice, lat_slice, offset_slice, step_slice] = data[
                    lon_slice, lat_slice, time_slice, step_slice
                ]


def sharedmem_worker(shm_spec, variable, gcs_path, slices, time_offset, worker_idx):

    # open the dataset from sharedmemory
    existing_shm = SharedMemory(name=shm_spec["name"])
    data = np.ndarray(
        shm_spec["shape"], dtype=shm_spec["dtype"], buffer=existing_shm.buf
    )

    # open the zarr
    store = gcsfs.GCSMap(root=gcs_path)
    z = zarr.open(store)

    # write each slice
    for ii_s, s in enumerate(slices):
        if ii_s % 100 == 0:
            logger.info(f"worker:{worker_idx}; ii_s:{ii_s}")

        time_slice = s[1]
        offset_slice = slice(s[1].start + time_offset, s[1].stop + time_offset)
        step_slice = s[2]
        lat_slice = s[3]
        lon_slice = s[4]
        z[variable][lon_slice, lat_slice, offset_slice, step_slice] = data[
            lon_slice, lat_slice, time_slice, step_slice
        ]

    # del data  # Unnecessary; merely emphasizing the array is no longer used
    existing_shm.close()

    return 1
