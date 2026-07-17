
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