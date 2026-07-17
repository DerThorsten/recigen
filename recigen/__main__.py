import argparse

from .package_type import PackageType
from .generate import generate_recipe
from .default_maintainer import get_default_maintainer
from pathlib import Path
import logging





def main():


    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="name of the package for which we want to generate the recipe")
    parser.add_argument(
        "--type",
        required=True,
        type=str,
        choices=[package_type.value for package_type in PackageType],
        help="type of the package for which we want to generate the recipe",
        dest="package_type"
    )
    parser.add_argument("--outdir", help="directory where the generated recipe should be saved",
                        default=Path.cwd(), type=Path)
    parser.add_argument("--maintainer", help="name of the maintainer of the package for which we want to generate the recipe", default=get_default_maintainer(), type=str)
    parser.add_argument("--version", help="version of the package for which we want to generate the recipe, if not provided, the latest version will be used")

    # log level
    parser.add_argument("--log-level", help="set the log level (default: INFO)", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))


    # make sure type a PackageType enum
    kwargs = vars(args)
    kwargs["package_type"] = PackageType(kwargs["package_type"])
    

    # showtime!
    generate_recipe(**kwargs)


if __name__ == "__main__":
    main()