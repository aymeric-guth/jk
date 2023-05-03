## INSTALLATION

```shell
python3 -m virtualenv .venv
source .venv/bin/activate
pip install --force-reinstall git+https://git.ars-virtualis.org/yul/jk
```

## CONFIGURATION

### .jk.yml

```yaml
---
executors:
  sh: &sh
    path: /bin/sh
    options: -c
    quote: true

pre-conditions: &pre-conditions-go
  env:
    GOPATH:

tasks:
  run:
    executor: *sh
    cmd: go run $PWD/main.go
    pre-conditions: *pre-conditions-go

  build:
    executor: *sh
    cmd: go build $PWD/main.go
    pre-conditions: *pre-conditions-go

  config:
    executor: *sh
    cmd: $EDITOR .jk.yml
    pre-conditions:
      validators:
        - '[ -f .jk.yml ]'

  clean:
    executor: *sh
    cmd: |
      rm main
    pre-conditions:
      validators:
        - '[ -f main ]'
```

### CONFIGURATION ADDITIONNELLE

```shell
# log level verbose
export JK_LOGLEVEL=INFO
# default
export JK_LOGLEVEL=ERROR
# path to libdir, see python package
export JK_LIBDIR=
# path to local config, defaults to $PWD/.jk.yml
export JK_LOCAL_CONFIG=.yml
```

## EXEMPLES

```shell
cd /tmp
git clone https://gitea.ars-virtualis.org/jolan/GoRun
cd GoRun
python3 -m virtualenv .venv
source .venv/bin/activate
pip install --force-reinstall git+https://git.ars-virtualis.org/yul/jk

jk build
jk run
jk clean
```
