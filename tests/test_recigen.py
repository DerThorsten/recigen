import pytest
import recigen
from recigen import generate_recipe



archived_cran_project = [
    "sirus"
]
@pytest.mark.parametrize("pkg_name", archived_cran_project)
def test_cran_pkgs_archived(pkg_name, tmp_path):
    generate_recipe(pkg_name, package_type=recigen.PackageType.r_cran, outdir=tmp_path, desired_version=None)


cran_projects = [
    "randomForest",
    "flashClust",
    "kde1d"
]
@pytest.mark.parametrize("pkg_name", cran_projects)
def test_cran_pkgs_regular(pkg_name, tmp_path):
    generate_recipe(pkg_name, package_type=recigen.PackageType.r_cran, outdir=tmp_path, desired_version=None)
