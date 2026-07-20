from textwrap import indent

import requests
from diskcache import Cache
from pathlib import Path
from ruamel.yaml import YAML
import yaml
from ..utils import  get_pkg_sha256
from .licences import get_rpkg_licence_information
import pprint
from packaging.version import parse as parse_version    
import re
from .r_utils import  r_ignorable_dependencies
import io
import tarfile
import tempfile
import requests
from bs4 import BeautifulSoup

# Creates a '.my_cache' directory in your project folder
cache = Cache(".emscripten_forge_cran_cache")


import logging

logger = logging.getLogger(__name__)




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
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    data = response.json()
    logger.info(f"Loaded metadata for {len(data):,} CRAN packages.")

    return data


def get_cran_data(package_name):
    """
    Returns the metadata for a single CRAN package from the cached
    CRAN database.
    """
    package_name = package_name.strip()

    cran_db = _get_cran_database()

    if package_name not in cran_db:
        raise ValueError(f"Package '{package_name}' not found in CRAN database.")

    return cran_db[package_name]




def get_highest_version(pkg_data):
    timeline = pkg_data.get("timeline", {})
    if not timeline:
        return None

    return max(
        timeline,
        key=lambda v: parse_version(v.replace("-", "."))
    )

def ensure_version(pkg_data, desired_version=None):
    
    timeline = pkg_data["timeline"]
    if desired_version is None:
        return get_highest_version(pkg_data)

    if desired_version in timeline:
        return desired_version
    else:
        raise ValueError(f"Version {desired_version} not found for package {pkg_data.get('Package')}.")
    


@cache.memoize(expire=36000)  # Caches results for 1 hour (3600 seconds)
def download_pkg(cran_data):
    version = cran_data.get("Version")
    name = cran_data.get("Package")
    if not version or not name:
        raise ValueError("CRAN data must contain 'Package' and 'Version' fields.")
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

def _extract_urls(cran_data):
    """
    Helper function to clean and split the CRAN 'URL' field into a list of individual URLs.
    Handles comma-separated, newline-separated, or whitespace-separated lists.
    """
    url_field = cran_data.get("URL", "")
    if not url_field:
        return []
    
    # Split by commas and/or newlines
    raw_urls = re.split(r'[,\n]+', url_field)
    
    # Clean up whitespace and filter out empty elements
    cleaned_urls = [url.strip() for url in raw_urls if url.strip()]
    return cleaned_urls

def guess_repo(cran_data):
    """
    Guesses the repository of a given R package.
    Prefers GitHub/GitLab/Bitbucket hosting URLs, otherwise falls back to 'CRAN' or 'Unknown'.
    """
    urls = _extract_urls(cran_data)
    
    # 1. Search for a development repository URL (prioritizing GitHub)
    repo_keywords = ["github.com", "gitlab.com", "bitbucket.org"]
    
    for keyword in repo_keywords:
        for url in urls:
            if keyword in url.lower():
                return url
    return None

def guess_homepage(cran_data):
    """
    Guesses a single homepage for the R package.
    Prefers documentation/pkgdown sites (like rstudio.github.io or r-lib.org),
    and falls back to any available URL if no specific documentation site is found.
    """
    urls = _extract_urls(cran_data)
    if not urls:
        return None
        
    # 1. Look for dedicated documentation/pkgdown homepages first (usually ends in .github.io, r-lib, etc.)
    # and avoid returning raw GitHub repositories as the "homepage" if a doc site exists.
    for url in urls:
        if "github.io" in url.lower() or "r-lib" in url.lower() or not "github.com" in url.lower():
            # Returns the first URL that doesn't look like a raw git repository code page
            return url
            
    # 2. Fallback: If only git repo URLs are left, return the first one
    return urls[0]



def cran_pkg_name_to_conda_name(cran_name):
    """
    Converts a CRAN package name to a conda package name.
    """
    # Convert to lowercase
    conda_name = cran_name.lower()
    
    # Replace spaces and hyphens with underscores
    conda_name = conda_name.replace(" ", "_").replace("-", "_")
    
    # Prefix with 'r-'
    conda_name = f"r-{conda_name}"
    
    return conda_name



def extract_dependencies(cran_data):

    build_deps = dict()
    run_deps = dict()
    host_deps = dict()



    # run dependencies
    # we need to look ad imports and depends, but not suggests or enhances
    imports_deps = cran_data.get("Imports", {})
    depends_deps = cran_data.get("Depends", {})
    import_and_deps = {**imports_deps, **depends_deps}
    if not import_and_deps:
        return []
    else:
        ret = []
        for name, version in import_and_deps.items():
            if name in r_ignorable_dependencies:
                continue
            conda_name = cran_pkg_name_to_conda_name(name)
            logger.info(f"Adding run  dep. {name} as {conda_name}: {version}")
            run_deps[conda_name] = version

    
    # host deps LinkingTo
    linking_to = cran_data.get("LinkingTo", {})
    logger.debug(f"linking to {linking_to}")
    for name, version in linking_to.items():
        if name in r_ignorable_dependencies:
            continue
        conda_name = cran_pkg_name_to_conda_name(name)
        logger.info(f"Adding host dep. {name} as {conda_name}: {version}")
        host_deps[conda_name] = version
        

    # build deps 
    # TODO, only after moving the fortran detection here,
    # we can fill these

    return dict(
        build=build_deps,
        host=host_deps,
        run=run_deps
    )



def extract_cran_examples(pkg):
    """
    Extract all Examples sections from a CRAN package reference manual.

    Parameters
    ----------
    pkg : str
        CRAN package name.

    Returns
    -------
    list of dict
        Each dict has:
            - function: function/topic name
            - example: example code as a string
    """
    url = f"https://cran.r-project.org/web/packages/{pkg}/refman/{pkg}.html"

    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    examples = []

    for h3 in soup.find_all("h3"):
        if h3.get_text(strip=True) != "Examples":
            continue

        code = h3.find_next("code")
        if code is None:
            continue

        # Find the nearest preceding h2, which contains the function/topic name
        h2 = h3.find_previous("h2")
        function = h2.get_text(" ", strip=True) if h2 else None

        examples.append({
            "function": function,
            "example": code.get_text()
        })

    return examples


def form_requirement(name, versioning_string):
    versioning_string = versioning_string.replace("-", "_")
    if versioning_string == "*":
        return name
    else:
        return f"{name} {versioning_string}"

def inspect_sources(pkg_dir):
    """
    Inspects the source directory of an R package to determine if it contains C/C++ or Fortran code.

    Parameters
    ----------
    pkg_dir : str or Path
        Path to the root directory of the R package source.

    Returns
    -------
    dict
        A dictionary with keys 'has_c_cpp' and 'has_fortran', indicating the presence of C/C++ and Fortran code, respectively.
    """
    pkg_dir = Path(pkg_dir)
    has_c_cpp = any(pkg_dir.rglob("*.c")) or any(pkg_dir.rglob("*.cpp")) or any(pkg_dir.rglob("*.cc"))
    has_fortran = any(pkg_dir.rglob("*.f")) or any(pkg_dir.rglob("*.f90")) or any(pkg_dir.rglob("*.f95"))

    return {
        "has_fortran": has_fortran
    }


def generate_r_cran_recipe(name, package_type, outdir , **kwargs):


    # generate a save lower case version of the package name for the output directory   
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    safe_name = f"r-{safe_name}"
    outdir = Path(outdir) / safe_name
    outdir.mkdir(parents=True, exist_ok=True)


    # load the template for the recipe.yaml
    template_path = Path(__file__).parent.parent / "templates" / "r_cran_recipe_template.yaml"
    
    # Initialize the YAML round-trip parser
    yaml = YAML()
    yaml.preserve_quotes = True

    template = yaml.load(template_path.read_text())
    metadata_all = get_cran_data(name)
    version = ensure_version(metadata_all, desired_version=kwargs.get("version"))

    # get the metadata for the specific version
    metadata = metadata_all.get("versions", {})[version]

    # extract the highest version if not provided, otherwise
    # ensure user provided version is valid


    cran_name = metadata.get("Package")
    
    needs_compilation = metadata.get("NeedsCompilation", "no")
    if needs_compilation.lower() == "no":
        raise ValueError(f"Package {name} does not need compilation. Only packages that need compilation are supported.")   
    
    title = metadata.get("Title")
    description = metadata.get("Description")
    version = metadata.get("Version")
    pkg_blob = download_pkg(metadata)
    sha256 = get_pkg_sha256(pkg_blob)

    # untargz
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(fileobj=io.BytesIO(pkg_blob), mode="r:gz") as tar:
            tar.extractall(path=tmpdir, filter="data")
        
        
        has_fortran = inspect_sources(tmpdir).get("has_fortran", False)
        logger.info(f"Package {cran_name} has Fortran code: {has_fortran}")



    # replace context/name and context/version in the template
    template["context"]["name"] = cran_name
    template["context"]["version"] = version


    ############################
    # source section
    ############################
    template["source"]["sha256"] = sha256

    ###########################
    # about section
    ###########################
    # handle repo
    repo = guess_repo(metadata)
    if repo is not None:
        template["about"]["repository"] = repo

    # homepage
    homepage = guess_homepage(metadata)
    if homepage is not None:
        template["about"]["homepage"] = homepage

    
    # license and license_family
    license, license_filenames = get_rpkg_licence_information(cran_license_string=metadata.get("License", ""), outdir=outdir)

    template["about"]["license"] = license
    template["about"]["license_file"] = license_filenames
    

    # summary (lets use the title as summary)
    template["about"]["summary"] = title
    
    # description
    template["about"]["description"] = description


    ############################
    # requirements section
    ############################
    deps = extract_dependencies(metadata)

    # for cross-compiulati
    deps['host'].update(deps['run'])
    deps['build'].update(deps['host'])

    if(deps['run']):
        template["requirements"]["run"] = []

    if has_fortran:
        template["requirements"]["build"].append("${{ compiler('fortran') }}")
        template["requirements"]["host"].append("libflang")

    for dep_type, dependencies in deps.items():
        logger.debug(f"{dependencies =}")
        for dep_name, dep_version in dependencies.items():
            req = form_requirement(dep_name, dep_version)
            template["requirements"][dep_type].append(req)


    ##############################
    # test-section
    ##############################





    with open(outdir / f"test_{cran_name}.R", "w") as f:

        # generate unit test file
        f.write(f"print('Loading {cran_name} package')\n")
        f.write(f"library({cran_name})\n")
        f.write(f"print('... {cran_name} package loaded successfully')\n\n")


        # try to extract examples from the CRAN reference manual
        examples = extract_cran_examples(cran_name)

        # filter out all examples containing "Not run" or "dontrun" (case insensitive)
        examples = [ex for ex in examples if not re.search(r"Not run|dontrun", ex["example"], re.IGNORECASE)]

        for i, example in enumerate(examples, start=1):
            ex = indent(example["example"].rstrip(), "    ")

            f.write(f"test_{i} <- function() {{\n")
            f.write(ex)
            f.write("\n}\n\n")

        # Run all tests
        for i in range(1, len(examples) + 1):
            f.write(f'print("Running test_{i}")\n')
            f.write(f"test_{i}()\n\n")
    
    ##############################
    # extra section
    ##############################
    template["extra"]["recipe-maintainers"] = [kwargs["maintainer"]]


    # 3. Programmatically insert a blank line BEFORE the 'tests' key
    # The second parameter is 'before', which adds a newline/comment block
    template.yaml_set_comment_before_after_key('tests', before='\n')

    # Set the width to infinity (or a massive number like 4096)
    yaml.width = float('inf')

    # save the recipe.yaml to the output directory
    recipe_path = outdir / "recipe.yaml"
    with open(recipe_path, "w") as f:
        yaml.dump(template, f)



    