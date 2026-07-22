
from diskcache import Cache
import requests
import io
import tarfile
import tempfile
from pathlib import Path

# Creates a '.my_cache' directory in your project folder
cache = Cache(".emscripten_forge_cran_cache")


r_builtin_packages = set([
    # Base Packages
    "base",
    "compiler",
    "datasets",
    "graphics",
    "grDevices",
    "grid",
    "methods",
    "parallel",
    "splines",
    "stats",
    "stats4",
    "tcltk",
    "tools",
    "translations",
    "utils",
])


r_ignorable_dependencies = set(r_builtin_packages)
r_ignorable_dependencies.add("R")



@cache.memoize(expire=36000)  # Caches results for 1 hour (3600 seconds)
def dowload_pkg_from_cran(name, version):

    cran_url_templates = [
        f"https://cran.r-project.org/src/contrib/{name}_{version}.tar.gz",
        f"https://cloud.r-project.org/src/contrib/{name}_{version}.tar.gz",
        f"https://cran.r-project.org/src/contrib/Archive/{name}/{name}_{version}.tar.gz"
    ]
    for url in cran_url_templates:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.content
        except requests.exceptions.RequestException:
            continue
    raise ValueError(f"Could not download package {name} version {version} from CRAN.")



def download_pkg_description_from_sources(pkg_name, version):

    pkg_blob = dowload_pkg_from_cran(pkg_name, version)

    # untargz
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(fileobj=io.BytesIO(pkg_blob), mode="r:gz") as tar:
            tar.extractall(path=tmpdir, filter="data")
            with open(Path(tmpdir)/pkg_name/"DESCRIPTION") as f:
                c = f.read()
                return c