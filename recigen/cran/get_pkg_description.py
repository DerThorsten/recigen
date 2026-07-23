from textwrap import indent
from packaging.version import Version
import re
import requests
from diskcache import Cache
from pathlib import Path

from .r_utils import (
    dowload_pkg_from_cran,
    download_pkg_description_from_sources
)


import pprint
from packaging.version import parse as parse_version    
import re
import io
import tarfile
import tempfile
import gzip
import subprocess
import pandas as pd
import email
import requests
from tqdm import tqdm
import logging


from rpy2.robjects import r

# Creates a '.my_cache' directory in your project folder
cache = Cache(".emscripten_forge_cran_cache")



logger = logging.getLogger(__name__)

CRAN_ARCHIVE_RDS_URL="https://cran.r-project.org/src/contrib/Meta/archive.rds"




def download_with_progress(url):
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    data = bytearray()

    with tqdm(
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc="Downloading"
    ) as bar:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                data.extend(chunk)
                bar.update(len(chunk))

    # Restore the downloaded content into the response object
    response._content = bytes(data)
    return response


@cache.memoize(expire=604800)
def _get_cran_database():
    """
    Downloads the full CRAN package metadata database from CRANDB.

    The result is cached for 7 days (168 hours).
    """
    url = "https://crandb.r-pkg.org/-/all"

    logger.info("Downloading full CRAN package database:")
    logger.info(" * this may take a while (tens of MBs) and can take up to 2 minutes depending on your connection.")
    logger.info(" * the result will be cached for 7 days, so this will only happen once per week.")
    response = download_with_progress(url)

    data = response.json()
    logger.info(f"Loaded metadata for {len(data):,} CRAN packages.")

    return data


def parse_description(text):
    """
    Convert R DESCRIPTION format into a CRANDB-like dict.
    """

    # DESCRIPTION follows RFC-822-ish rules
    msg = email.message_from_string(text)

    data = {}

    for key, value in msg.items():
        # Normalize multiline fields
        value = " ".join(
            line.strip()
            for line in value.splitlines()
        )

        data[key] = value

    # Fields CRANDB commonly normalizes as dicts!!!!
    for field in [
        "Depends",
        "Imports",
        "Suggests",
        "LinkingTo",
    ]:
        if field in data:

            pkgs = [
                x.strip()
                for x in data[field].split(",")
            ]
            pkgs_to_ver = dict()
            for pkg_str in pkgs:
                splitted = pkg_str.split(' ',1)
                name = splitted[0]
                version = "*"
                if len(splitted) == 2:
                    version = splitted[1].strip('(').strip(')')

                pkgs_to_ver[name] = version
            data[field] = pkgs_to_ver
        
    return data



def _get_exisiting_versions_for_archived_pkg(pkg_name):
    with tempfile.TemporaryDirectory() as td:
        rds_path = f"{td}/archive.rds"
        csv_path = f"{td}/archive.csv"

        logger.info("downloading archive")

        r = requests.get(CRAN_ARCHIVE_RDS_URL, timeout=60)
        r.raise_for_status()

        with open(rds_path, "wb") as f:
            f.write(gzip.decompress(r.content))

        logger.info("extracting package %s", pkg_name)


        r(f'''
        x <- readRDS("{rds_path}")

        if (!("{pkg_name}" %in% names(x))) {{
            stop("Package not found: {pkg_name}")
        }}

        df <- x[["{pkg_name}"]]
        df$file <- rownames(df)
        rownames(df) <- NULL

        write.csv(df, "{csv_path}", row.names = FALSE)
        ''')

        df =  pd.read_csv(csv_path)

        def extract_version(path):
            name, name_and_ver = path.split("/")
            name_and_ver=name_and_ver.replace(".tar.gz","")
            ver = name_and_ver[len(name) + 1: ]
            return ver
        return df["file"].apply(extract_version)



def _get_description_for_archived_pkg(pkg_name, desired_version):

    if desired_version is None:
        versions = _get_exisiting_versions_for_archived_pkg(pkg_name)
        version = max(
            versions,
            key=lambda v: parse_version(v.replace("-", "."))
        )

    else:
        version = desired_version
    desc_str = download_pkg_description_from_sources(pkg_name, version=version)

    data =  parse_description(desc_str)
    data["_is_archived"] = True
    return data


    

def ensure_version(pkg_data, desired_version=None):
    
    timeline = pkg_data["timeline"]
    if desired_version is None:
        return max(
            timeline,
            key=lambda v: parse_version(v.replace("-", "."))
        )

    if desired_version in timeline:
        return desired_version
    else:
        raise ValueError(f"Version {desired_version} not found for package {pkg_data.get('Package')}.")
    


def get_pkg_description(pkg_name, desired_version):
    pkg_name = pkg_name.strip()

    # all **non-archived** pkgs should be in the cran db
    cran_db = _get_cran_database()
    if pkg_name in cran_db:
        pkg_data = cran_db[pkg_name]
        version = ensure_version(pkg_data, desired_version)
        data = pkg_data['versions'][version]
        data["_is_archived"] = False
        return data
        
    # the pkg **was not** found in the cran db
    # this means **it could be ** archived
    logger.info(f"Package {pkg_name} not found in CRAN database, trying archive")
    return  _get_description_for_archived_pkg(pkg_name, desired_version)
    