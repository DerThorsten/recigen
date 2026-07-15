import subprocess

def get_default_maintainer():
    # try to get git user.name from git config
    try:

        maintainer = (
            subprocess.check_output(["git", "config", "--get", "user.name"])
            .decode("utf-8")
            .strip()
        )
        if maintainer:
            return maintainer
    except Exception as e:
        # show warning but don't fail
        print(f"Warning: Could not get git user.name from git config: {e}")
    return "Todo"