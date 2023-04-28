## Initial Bootsrapping

``` shell
git clone gitea.ars-virtualis.org/yul/jk-proto
cd jk-proto
python3 -m virtualenv .venv
source .venv/bin/activate
pip install -r requirements
python -m build . --wheel
python -m pip install --force-reinstall dist/*py3-none-any.whl
```

## Commands

```shell
# open jk local config file
jk config
# execute run command
jk run
# build the project as a wheel
jk build
# install newly built version in virtualenv
jk deploy
# clean build artifacts
jk clean
# re-install virtualenv + dev dependencies, requires zsh, direnv
jk env
```
