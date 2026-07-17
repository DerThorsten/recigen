
from pathlib import Path


import logging
logger = logging.getLogger(__name__)

spdx_license_mapping = {
    # GPL family
    "GPL-2": "GPL-2.0-only",
    "GPL-3": "GPL-3.0-only",
    "GPL (>= 2)": "GPL-2.0-or-later",
    "GPL (>= 3)": "GPL-3.0-or-later",
    "GPL-2 | GPL-3": "GPL-2.0-or-later",
    
    # LGPL family
    "LGPL-2": "LGPL-2.0-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-3": "LGPL-3.0-only",
    "LGPL (>= 2)": "LGPL-2.0-or-later",
    "LGPL (>= 2.1)": "LGPL-2.1-or-later",
    "LGPL (>= 3)": "LGPL-3.0-or-later",
    "LGPL-2 | LGPL-3": "LGPL-2.0-or-later",
    
    # AGPL family
    "AGPL-3": "AGPL-3.0-only",
    "AGPL (>= 3)": "AGPL-3.0-or-later",
    
    # BSD & MIT family
    "MIT": "MIT",
    "BSD_2_clause": "BSD-2-Clause",
    "BSD_3_clause": "BSD-3-Clause",
    
    # Apache & Creative Commons
    "Apache License 2.0": "Apache-2.0",
    "Apache License (== 2.0)": "Apache-2.0",
    "CC0": "CC0-1.0",

    # Unlimited
    "Unlimited": "LicenseRef-Unlimited",
}

# r ships certain licences at  - ${{ PREFIX }}/lib/R/share/licenses/<>
# here is a set of the files that are shipped with r-base at the folder $PREFIX/lib/R/share/licenses
r_base_shipped_licenses = {
    "Apache-2.0",
    "Artistic-2.0",
    "BSD_2_clause",
    "BSD_3_clause",
    "CC0-1.0",
    "GPL-2",
    "GPL-3",
    "LGPL-2",
    "LGPL-2.1",
    "LGPL-3",
    "MIT",
}


spdx_license_to_r_base_shipped_license_file = {
    # Apache
    "Apache-2.0": "Apache-2.0",

    # Artistic
    "Artistic-2.0": "Artistic-2.0",

    # BSD
    "BSD-2-Clause": "BSD_2_clause",
    "BSD-3-Clause": "BSD_3_clause",

    # CC
    "CC0-1.0": "CC0-1.0",

    # GPL
    "GPL-2.0-only": "GPL-2",
    "GPL-2.0-or-later": "GPL-2",
    "GPL-3.0-only": "GPL-3",
    "GPL-3.0-or-later": "GPL-3",

    # LGPL
    "LGPL-2.0-only": "LGPL-2",
    "LGPL-2.0-or-later": "LGPL-2",
    "LGPL-2.1-only": "LGPL-2.1",
    "LGPL-2.1-or-later": "LGPL-2.1",
    "LGPL-3.0-only": "LGPL-3",
    "LGPL-3.0-or-later": "LGPL-3",

    # MIT
    "MIT": "MIT",
}


UNLIMITED_LICENSE_TEXT = """
No restrictions on distribution or use other than those imposed by relevant laws (including copyright laws).

See https://cran.r-project.org/doc/manuals/r-release/R-exts.html#Licensing
"""

def get_rpkg_licence_information(cran_license_string, outdir):

    logger.debug(f"cran_license_string={cran_license_string}")
    # we want to get at least:
    # - license
    # - license_file

    # we **DO NOT** need the license_family because its deprecated

    # we may need to write a custom file to the recipe directory 

    licenses = []

    # explict licenses like  | file LICENCE
    filenames = []

    # split the license string by " | " to handle multiple licenses
    license_strings = cran_license_string.split("|")

    # strip whitespace and parentheses from each license
    license_strings = [license_str.strip() for license_str in license_strings]

    
    for license_str in license_strings:
        if "file LICENCE" in license_str:
            filenames.append("LICENCE")
        else:
            spdx_license = spdx_license_mapping.get(license_str, license_str)
            licenses.append(spdx_license)
            if spdx_license == "LicenseRef-Unlimited":
                # write a custom file to the recipe directory
                license_file_path = Path(outdir) / "LICENSE"
                with open(license_file_path, "w") as f:
                    f.write(UNLIMITED_LICENSE_TEXT)
                filenames.append("LICENSE")
            else:
                # r ships certain licences
                shipped_license_file = spdx_license_to_r_base_shipped_license_file.get(spdx_license)
                if shipped_license_file:
                    filenames.append(shipped_license_file)
                else:
                    filename = f"TODO_add_license_file_for_{spdx_license}"
                    filenames.append(filename)  
    
    return licenses, filenames
        