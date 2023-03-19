#!/usr/bin/python3

import argparse
import os
import rpm
import selinux
import subprocess
import sys
from podman import PodmanClient
from termcolor import cprint

# import podman variables from local file
sys.dont_write_bytecode = True
from podman_variables import *


def print_yes():
    cprint(' [YES]', 'green')


def print_no():
    cprint(' [NO]', 'red')


def print_soft_no():
    cprint(' [NO]', 'yellow', attrs=['bold','dark'])


def print_success():
    cprint(' [SUCCESS]', 'green')


def print_failure():
    cprint(' [FAILURE]', 'red')


def print_debug(msg, cmd):
    cprint(f'DEBUG: {msg}:', 'yellow')
    cprint(f'{cmd}\n', 'yellow', attrs=['bold'])


def check_podman_installed():
    cprint('{0:.<70}'.format('PODMAN: is podman installed'), 'yellow', end='')
    podman_installed = None
    ts = rpm.TransactionSet()
    rpm_listing = ts.dbMatch()

    for rpm_pkg in rpm_listing:
        if rpm_pkg['name'] == 'podman':
            podman_installed = True

    if podman_installed:
        print_yes()
    else:
        print_no()
        cprint('\npodman is not installed', 'magenta')
        cprint('Exiting...', 'red')
        sys.exit(1)


def ensure_podman_socket_running():
    if os.geteuid() == 0:
        user = ''
    else:
        user = '--user '

    cmd_str = f'systemctl {user} is-active --quiet podman.socket'
    cmd = cmd_str.split()
    cmd_output = subprocess.run(cmd)

    if cmd_output.returncode == 0:
        return

    cprint('PODMAN: starting podman.socket...', 'yellow')

    cmd_str = f'systemctl {user}start podman.socket'
    cmd = cmd_str.split()
    cmd_output = subprocess.run(cmd, capture_output=True, universal_newlines=True)

    if args.debug:
        print_debug('to manually start podman.socket', cmd_str)

    if cmd_output.returncode != 0:
        err_output = cmd_output.stderr.rstrip()
        cprint(err_output, 'red', attrs=['bold'])
        sys.exit(2)


def ensure_image_exists():
    cprint('{0:.<70}'.format('PODMAN: checking if image exists'), 'yellow', end='')
    podman_image = client.images.list(filters = {'reference' : image_name})

    if podman_image:
        print_yes()
    else:
        print_soft_no()
        cprint('PODMAN: building image...', 'yellow')
        # using the api function will hide the build process
        # use subprocess so we can see it in real-time
        # client.images.build(path=cur_dir, tag=image_name, squash=True, rm=True)
        podman_cmd_str = f'podman build --squash -t {image_name} {cur_dir}'
        podman_cmd = podman_cmd_str.split()

        if args.debug:
            print_debug('to manually build the image', podman_cmd_str)

        cmd_output = subprocess.run(podman_cmd, universal_newlines=True)
        cprint('{0:.<70}'.format('PODMAN: build image'), 'yellow', end='')

        if cmd_output.returncode != 0:
            print_failure()
            cprint('Exiting...', 'red')
            sys.exit(3)
        else:
            print_success()


def ensure_image_removed():
    cprint('{0:.<70}'.format('PODMAN: checking if image exists'), 'yellow', end='')
    podman_image_exists = client.images.list(filters = {'reference' : image_name})

    if podman_image_exists:
        print_yes()
        cprint('PODMAN: removing image...', 'yellow')
        client.images.remove(image=image_name)
    else:
        print_soft_no()


def ensure_container_exists_and_running(interactive):
    cprint('{0:.<70}'.format('PODMAN: checking if container exists'), 'yellow', end='')
    container_exists = client.containers.list(all=True, filters = {'name' : container_name})

    if container_exists:
        print_yes()
        podman_container = client.containers.get(container_name)
        container_status = podman_container.status

        cprint('{0:.<70}'.format('PODMAN: checking if container is running'), 'yellow', end='')

        if container_status == 'running':
            print_yes()
            return
        else:
            print_soft_no()
            cprint('PODMAN: starting container...', 'yellow')
            if args.debug:
                print_debug('to manually start the container', f'podman start {container_name}')
            podman_container.start()
            ensure_container_exists_and_running(interactive)
    else:
        print_soft_no()
        run_container(interactive)
        if interactive:
            ensure_container_exists_and_running(interactive)


def ensure_container_stopped_removed(remove_container=True):
    cprint('{0:.<70}'.format('PODMAN: checking if container exists'), 'yellow', end='')
    container_exists = client.containers.list(all=True, filters = {'name' : container_name})

    if container_exists:
        print_yes()
        podman_container = client.containers.get(container_name)
        container_status = podman_container.status

        cprint('{0:.<70}'.format('PODMAN: checking if container is running'), 'yellow', end='')

        if container_status == 'running':
            print_yes()
            cprint('PODMAN: stopping container...', 'yellow')
            if args.debug:
                print_debug('to manually stop the container', f'podman stop {container_name}')
            podman_container.stop()
            if remove_container:
                # in the event that auto-remove is set the container may already be deleted
                ensure_container_stopped_removed(remove_container)
                return
        else:
            print_soft_no()

        if remove_container:
            cprint('PODMAN: removing container...', 'yellow')
            if args.debug:
                print_debug('to manually remove the container', f'podman rm {container_name}')
            podman_container.remove()
    else:
        print_soft_no()


def set_selinux_context_t():
    container_context_t = 'container_file_t'
    dir_file_paths = []

    for vol in bind_volumes:
        host_dir = None
        recursive = None

        if vol['selinux_label']:
            host_dir = vol['source']
            recursive = vol['selinux_recursive']

            if not recursive:
                dir_file_paths.append(host_dir)
            else:
                for dir_path, dirs, files in os.walk(host_dir):
                    for filename in files:
                        file_path = os.path.join(dir_path,filename)
                        dir_file_paths.append(file_path)

                    dir_file_paths.append(dir_path)

    if not dir_file_paths:
        return

    cprint('{0:.<70}'.format('PODMAN: selinux label check'), 'yellow', end='')

    for dir_file_path in dir_file_paths:
        ret, mount_dir_context = selinux.getfilecon(dir_file_path)

        if ret < 0:
            print_failure()
            cprint(f'selinux.getfilecon({dir_file_path}) failed....exiting', red)
            sys.exit(4)

        mount_dir_context_t = mount_dir_context.split(':')[2]
        if mount_dir_context_t != container_context_t:
            mount_dir_context = mount_dir_context.replace(mount_dir_context_t, container_context_t)
            selinux.setfilecon(dir_file_path, mount_dir_context)

    print_yes()


def create_podman_vol_str():
    mount_vol_list = []

    if not bind_volumes:
        return ''

    for vol in bind_volumes:
        option = ''
        if vol['read_only']:
            option = ':ro'
        mount_vol_list.append(f"-v {vol['source']}:{vol['target']}{option} ")

    mount_vol_str = ''.join(mount_vol_list).rstrip()

    return mount_vol_str


def run_container(interactive):
    if selinux.is_selinux_enabled():
        set_selinux_context_t()

    cprint('PODMAN: run container...', 'yellow')
    podman_vol_str = create_podman_vol_str()

    if privileged:
        privileged_str = '--privileged '
    else:
        privileged_str = ''

    if interactive:
        podman_cmd_str = f'podman run -d -it {privileged_str}{podman_vol_str} -h {container_hostname} --name {container_name} {image_name}'
        if args.debug:
            print_debug('to manually run the container', podman_cmd_str)

        client.containers.run(image=image_name, name=container_name, hostname=container_hostname, detach=True, tty=True, privileged=privileged, mounts=bind_volumes)

    else:
        podman_cmd_str = f'podman run -it --rm {privileged_str}{podman_vol_str} -h {container_hostname} --name {container_name} {image_name} {container_script}'
        podman_cmd = podman_cmd_str.split()

        if args.debug:
            print_debug('to manually run the container', podman_cmd_str)

        cprint(f'PODMAN: running command {container_script}', 'yellow')
        # using the api function will hide the script output
        # use subprocess so we can see it in real-time
        # client.containers.run(image=image_name, name=container_name, hostname=container_hostname, detach=True, auto_remove=True, mounts=bind_volumes, command=container_script)
        cmd_output = subprocess.run(podman_cmd, universal_newlines=True)
        cprint('{0:.<70}'.format(f'PODMAN: running {container_script}'), 'yellow', end='')

        if cmd_output.returncode != 0:
            print_failure()
            cprint('Exiting...', 'red')
            sys.exit(5)
        else:
            print_success()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()

    parser.add_argument('--auto',
                        action='store_true',
                        help='ensure image is built, then run container_script in a non-interactive container',
                        default=False)
    parser.add_argument('--debug',
                        action='store_true',
                        help='display debug messages',
                        default=False)
    group.add_argument('--rebuild',
                        action='store_true',
                        help='remove podman image and container if they exist, '
                             'then build (new) podman image and run container',
                        default=False)
    group.add_argument('--rerun',
                        action='store_true',
                        help='remove container if it exists, then (re-)run it',
                        default=False)
    group.add_argument('--restart',
                        action='store_true',
                        help='stop the container if it exists, then (re-)run it',
                        default=False)
    group.add_argument('--rm_image',
                        action='store_true',
                        help='remove podman image and container if they exist',
                        default=False)
    group.add_argument('--rm_container',
                        action='store_true',
                        help='remove container if it exists',
                        default=False)
    group.add_argument('--stop_container',
                        help='stop podman container it exists and is running',
                        action='store_true',
                        default=False)

    args = parser.parse_args()

    check_podman_installed()
    ensure_podman_socket_running()

    if os.geteuid() == 0:
        client = PodmanClient(base_url='unix:/run/podman/podman.sock')
    else:
        client = PodmanClient()

    if args.auto:
        interactive = False
    else:
        interactive = True

    if args.rm_image or args.rebuild:
        ensure_container_stopped_removed()
        ensure_image_removed()
        if args.rm_image: sys.exit()

    if args.rm_container or args.rerun:
        ensure_container_stopped_removed()
        if args.rm_container: sys.exit()

    if args.stop_container or args.restart:
        ensure_container_stopped_removed(remove_container=False)
        if args.stop_container: sys.exit()

    if not interactive and not args.rebuild:
        ensure_container_stopped_removed()

    cprint('{0:.<70}'.format('PODMAN: image name'), 'yellow', end='')
    cprint(f' {image_name}', 'cyan')

    ensure_image_exists()

    cprint('{0:.<70}'.format('PODMAN: container name'), 'yellow', end='')
    cprint(f' {container_name}', 'cyan')

    ensure_container_exists_and_running(interactive)

    if interactive:
        cprint('PODMAN: to login to the container run:', 'yellow')
        cprint(f'podman exec -it {container_name} /bin/bash\n', 'green')
