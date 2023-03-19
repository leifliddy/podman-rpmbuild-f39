# podman-rpmbuild
creates a package build environment for Fedora

**Fedora Package install**  
```
dnf install podman python3-podman python3-termcolor
```

**build container and login to it**  
```
git clone https://github.com/leifliddy/podman-rpmbuild-f38.git
cd podman-rpmbuild-f38  

# this will build the image and run the container   
./script-podman.py

# login to the container 
podman exec -it rpm_builder_f38 /bin/bash

# exit container
Control+D or exit
```

**script-podman.py options**  
these should be pretty self-explanatory
```
usage: script-podman.py [-h] [--debug]
                        [--rebuild | --rerun | --restart | --rm_image | --rm_container | --stop_container]

options:
  -h, --help        show this help message and exit
  --debug           display debug messages
  --rebuild         remove podman image and container if they exist, then build (new) podman image and run container
  --rerun           remove container if it exists, then (re-)run it
  --restart         stop the container if it exists, then (re-)run it
  --rm_image        remove podman image and container if they exist
  --rm_container    remove container if it exists
  --stop_container  stop podman container it exists and is running
```
