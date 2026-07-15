import requests
from diskcache import Cache
from pathlib import Path
from ruamel.yaml import YAML
import yaml
from .utils import  get_pkg_sha256
import pprint
from packaging.version import parse as parse_version    
import re



# Creates a '.my_cache' directory in your project folder
cache = Cache(".emscripten_forge_cran_cache")



@cache.memoize(expire=604800)
def _get_cran_database():
    """
    Downloads the full CRAN package metadata database from CRANDB.

    The result is cached for 7 days (168 hours).
    """
    url = "https://crandb.r-pkg.org/-/all"

    print("Downloading full CRAN package database:")
    print(" * this may take a while (tens of MBs) and can take up to 2 minutes depending on your connection.")
    print(" * the result will be cached for 7 days, so this will only happen once per week.")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    data = response.json()
    print(f"Loaded metadata for {len(data):,} CRAN packages.")

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
                
    # 2. Fallback: Check if the package is explicitly hosted on the main CRAN repo
    if cran_data.get("Repository") == "CRAN":
        return "CRAN"
        
    return "Unknown"


def guess_homepage(cran_data):
    """
    Guesses a single homepage for the R package.
    Prefers documentation/pkgdown sites (like rstudio.github.io or r-lib.org),
    and falls back to any available URL if no specific documentation site is found.
    """
    urls = _extract_urls(cran_data)
    if not urls:
        return "Unknown"
        
    # 1. Look for dedicated documentation/pkgdown homepages first (usually ends in .github.io, r-lib, etc.)
    # and avoid returning raw GitHub repositories as the "homepage" if a doc site exists.
    for url in urls:
        if "github.io" in url.lower() or "r-lib" in url.lower() or not "github.com" in url.lower():
            # Returns the first URL that doesn't look like a raw git repository code page
            return url
            
    # 2. Fallback: If only git repo URLs are left, return the first one
    return urls[0]

def get_spdx_and_family(cran_data):
    cran_license = cran_data.get("License", "").strip()
    if not cran_license:
        return {"license": "Unknown", "license_family": "Unknown"}

    # 1. Clean up CRAN noise (+ file LICENSE, etc.)
    cleaned = re.sub(r"\s*\+\s*file\s+LICENSE", "", cran_license, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*file\s+LICENSE", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("file LICENSE", "").strip()

    # 2. Comprehensive mapping table: { CRAN_STRING: (SPDX_ID, FAMILY) }
    license_mapping = {
        # GPL family
        "GPL-2": ("GPL-2.0-only", "GPL"),
        "GPL-3": ("GPL-3.0-only", "GPL"),
        "GPL (>= 2)": ("GPL-2.0-or-later", "GPL"),
        "GPL (>= 3)": ("GPL-3.0-or-later", "GPL"),
        "GPL-2 | GPL-3": ("GPL-2.0-or-later", "GPL"),
        
        # LGPL family
        "LGPL-2": ("LGPL-2.0-only", "LGPL"),
        "LGPL-2.1": ("LGPL-2.1-only", "LGPL"),
        "LGPL-3": ("LGPL-3.0-only", "LGPL"),
        "LGPL (>= 2)": ("LGPL-2.0-or-later", "LGPL"),
        "LGPL (>= 2.1)": ("LGPL-2.1-or-later", "LGPL"),
        "LGPL (>= 3)": ("LGPL-3.0-or-later", "LGPL"),
        "LGPL-2 | LGPL-3": ("LGPL-2.0-or-later", "LGPL"),
        
        # AGPL family
        "AGPL-3": ("AGPL-3.0-only", "AGPL"),
        "AGPL (>= 3)": ("AGPL-3.0-or-later", "AGPL"),
        
        # BSD & MIT family
        "MIT": ("MIT", "MIT"),
        "BSD_2_clause": ("BSD-2-Clause", "BSD"),
        "BSD_3_clause": ("BSD-3-Clause", "BSD"),
        
        # Apache & Creative Commons
        "Apache License 2.0": ("Apache-2.0", "Apache"),
        "Apache License (== 2.0)": ("Apache-2.0", "Apache"),
        "CC0": ("CC0-1.0", "CC0"),
    }

    # 3. Direct Match Check
    if cleaned in license_mapping:
        spdx, family = license_mapping[cleaned]
        return {"license": spdx, "license_family": family}

    # 4. Handle logical ORs (e.g. "GPL-2 | GPL-3")
    if " | " in cleaned:
        parts = [p.strip() for p in cleaned.split("|")]
        # Pull SPDX and Family mapping for each part if they exist
        mapped_parts = [license_mapping.get(p) for p in parts if p in license_mapping]
        
        if len(mapped_parts) == len(parts):
            spdx_list = [item[0] for item in mapped_parts]
            family_list = sorted(list(set(item[1] for item in mapped_parts))) # Unique families
            
            return {
                "license": " OR ".join(spdx_list),
                "license_family": " or ".join(family_list) if len(family_list) > 1 else family_list[0]
            }

    # 5. Fallback: Parse family string from cleaned text if not in dict
    fallback_family = "Unknown"
    for keyword in ["GPL", "LGPL", "AGPL", "BSD", "MIT", "Apache", "CC0"]:
        if keyword in cleaned.upper():
            fallback_family = keyword
            break

    return {
        "license": f"LicenseRef-{cleaned}" if cleaned else "Unknown",
        "license_family": fallback_family
    }






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
    # only use imports
    imports = cran_data.get("Imports", "")
    if not imports:
        return []
    else:
        ret = []
        # Split imports by comma and strip whitespace
        for name, version in imports.items():
            print(f"Dependency: {name}, Version: {version}")
            conda_name = cran_pkg_name_to_conda_name(name)
            print(f"Converted to conda name: {conda_name}")
            ret.append((conda_name, version))

        return ret



def make_licence_file_filename(license_name):
    #  GPL-2.0-or-later will be mapped to GPL-2
    if license_name.startswith("GPL-2"):
        return "GPL-2"
    elif license_name.startswith("GPL-3"):
        return "GPL-3"
    elif license_name.startswith("LGPL-2"):
        return "LGPL-2"
    elif license_name.startswith("LGPL-3"):
        return "LGPL-3"
    else:
        return "TODO"  # Default case for unknown licenses



def generate_r_cran_recipe(name, package_type, outdir , **kwargs):


    # generate a save lower case version of the package name for the output directory   
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    safe_name = f"r-{safe_name}"
    outdir = Path(outdir) / safe_name
    outdir.mkdir(parents=True, exist_ok=True)


    # load the template for the recipe.yaml
    template_path = Path(__file__).parent / "templates" / "r_cran_recipe_template.yaml"
    
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
    template["about"]["repository"] = guess_repo(metadata)

    # homepage
    template["about"]["homepage"] = guess_homepage(metadata)    

    
    # license and license_family
    license_info = get_spdx_and_family(metadata)
    template["about"]["license"] = license_info["license"]
    template["about"]["license_family"] = license_info["license_family"]
    
    # load license file from licence folder
    template["about"]["license_file"] = [R"${{ PREFIX }}/lib/R/share/licenses/" + make_licence_file_filename(license_info["license"])]
    

    # summary (lets use the title as summary)
    template["about"]["summary"] = title
    
    # description
    template["about"]["description"] = description


    ############################
    # requirements section
    ############################
    dependencies = extract_dependencies(metadata)
    if(dependencies):
       # add run section to dependencies
       template["requirements"]["run"] = []
       for dep_name, dep_version in dependencies:
           # add the dependency to the run section
           template["requirements"]["build"].append(f"{dep_name} {dep_version}")
           template["requirements"]["host"].append(f"{dep_name} {dep_version}")
           template["requirements"]["run"].append(f"{dep_name} {dep_version}")

    ##############################
    # test-section
    ##############################
    # generate unit test file
    content = f"library({cran_name})"
    with open(outdir / f"test_{cran_name}.R", "w") as f:
        f.write(content)

        
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

