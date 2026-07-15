
# enum
from .package_type import PackageType

from .cran import generate_r_cran_recipe







def generate_recipe(name, package_type, **kwargs):
    if package_type == PackageType.r_cran:
        generate_r_cran_recipe(name, package_type, **kwargs)
    else:
        raise ValueError(f"package of type / source {package_type} is not supported yet. Please open an issue on github if you want to see this type supported.")
    