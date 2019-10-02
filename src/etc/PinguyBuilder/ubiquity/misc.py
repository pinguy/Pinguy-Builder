# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-

from collections import namedtuple
import contextlib
import grp
import os
import pwd
import re
import shutil
import subprocess
import syslog

from ubiquity import osextras


def utf8(s, errors="strict"):
    """Decode a string as UTF-8 if it isn't already Unicode."""
    if isinstance(s, str):
        return s
    else:
        return str(s, "utf-8", errors)


def is_swap(device):
    try:
        with open('/proc/swaps') as fp:
            for line in fp:
                if line.startswith(device + ' '):
                    return True
    except Exception:
        pass
    return False


_dropped_privileges = 0


def set_groups_for_uid(uid):
    if uid == os.geteuid() or uid == os.getuid():
        return
    user = pwd.getpwuid(uid).pw_name
    try:
        os.setgroups([g.gr_gid for g in grp.getgrall() if user in g.gr_mem])
    except OSError:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)


def drop_all_privileges():
    # gconf needs both the UID and effective UID set.
    global _dropped_privileges
    uid = os.environ.get('PKEXEC_UID')
    gid = None
    if uid is not None:
        uid = int(uid)
        set_groups_for_uid(uid)
        gid = pwd.getpwuid(uid).pw_gid
    if gid is not None:
        gid = int(gid)
        os.setregid(gid, gid)
    if uid is not None:
        uid = int(uid)
        os.setreuid(uid, uid)
        os.environ['HOME'] = pwd.getpwuid(uid).pw_dir
        os.environ['LOGNAME'] = pwd.getpwuid(uid).pw_name
    _dropped_privileges = None


def drop_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    if _dropped_privileges == 0:
        uid = os.environ.get('PKEXEC_UID')
        gid = None
        if uid is not None:
            uid = int(uid)
            set_groups_for_uid(uid)
            gid = pwd.getpwuid(uid).pw_gid
        if gid is not None:
            gid = int(gid)
            os.setegid(gid)
        if uid is not None:
            os.seteuid(uid)
    _dropped_privileges += 1


def regain_privileges():
    global _dropped_privileges
    assert _dropped_privileges is not None
    _dropped_privileges -= 1
    if _dropped_privileges == 0:
        os.seteuid(0)
        os.setegid(0)
        os.setgroups([])


def drop_privileges_save():
    """Drop the real UID/GID as well, and hide them in saved IDs."""
    # At the moment, we only know how to handle this when effective
    # privileges were already dropped.
    assert _dropped_privileges is not None and _dropped_privileges > 0
    uid = os.environ.get('PKEXEC_UID')
    gid = None
    if uid is not None:
        uid = int(uid)
        set_groups_for_uid(uid)
        gid = pwd.getpwuid(uid).pw_gid
    if gid is not None:
        gid = int(gid)
        os.setresgid(gid, gid, 0)
    if uid is not None:
        os.setresuid(uid, uid, 0)


def regain_privileges_save():
    """Recover our real UID/GID after calling drop_privileges_save."""
    assert _dropped_privileges is not None and _dropped_privileges > 0
    os.setresuid(0, 0, 0)
    os.setresgid(0, 0, 0)
    os.setgroups([])


@contextlib.contextmanager
def raised_privileges():
    """As regain_privileges/drop_privileges, but in context manager style."""
    regain_privileges()
    try:
        yield
    finally:
        drop_privileges()


def raise_privileges(func):
    """As raised_privileges, but as a function decorator."""
    from functools import wraps

    @wraps(func)
    def helper(*args, **kwargs):
        with raised_privileges():
            return func(*args, **kwargs)

    return helper


@raise_privileges
def grub_options():
    """ Generates a list of suitable targets for grub-installer
        @return empty list or a list of ['/dev/sda1','Ubuntu Hardy 8.04'] """
    from ubiquity.parted_server import PartedServer

    ret = []
    try:
        oslist = {}
        subp = subprocess.Popen(
            ['os-prober'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        result = subp.communicate()[0].splitlines()
        for res in result:
            res = res.split(':')
            res[0] = re.match(r'[/\w\d]+', res[0]).group()
            oslist[res[0]] = res[1]
        p = PartedServer()
        for disk in p.disks():
            p.select_disk(disk)
            with open(p.device_entry('model')) as fp:
                mod = fp.readline()
            with open(p.device_entry('device')) as fp:
                dev = fp.readline()
            with open(p.device_entry('size')) as fp:
                size = fp.readline()
            if dev and mod:
                if size.isdigit():
                    size = format_size(int(size))
                    ret.append([dev, '%s (%s)' % (mod, size)])
                else:
                    ret.append([dev, mod])
            for part in p.partitions():
                ostype = ''
                if part[4] == 'linux-swap':
                    continue
                if part[4] == 'free':
                    continue
                if os.path.exists(p.part_entry(part[1], 'format')):
                    # Don't bother looking for an OS type.
                    pass
                elif part[5] in oslist.keys():
                    ostype = oslist[part[5]]
                ret.append([part[5], ostype])
    except Exception:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    return ret


@raise_privileges
def boot_device():
    from ubiquity.parted_server import PartedServer

    boot = None
    root = None
    try:
        p = PartedServer()
        for disk in p.disks():
            p.select_disk(disk)
            for part in p.partitions():
                part = part[1]
                if p.has_part_entry(part, 'mountpoint'):
                    mp = p.readline_part_entry(part, 'mountpoint')
                    if mp == '/boot':
                        boot = disk.replace('=', '/')
                    elif mp == '/':
                        root = disk.replace('=', '/')
    except Exception:
        import traceback
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    if boot:
        return boot
    return root


def is_removable(device):
    if device is None:
        return None
    device = os.path.realpath(device)
    devpath = None
    is_partition = False
    removable_bus = False
    subp = subprocess.Popen(['udevadm', 'info', '-q', 'property',
                             '-n', device],
                            stdout=subprocess.PIPE, universal_newlines=True)
    for line in subp.communicate()[0].splitlines():
        line = line.strip()
        if line.startswith('DEVPATH='):
            devpath = line[8:]
        elif line == 'DEVTYPE=partition':
            is_partition = True
        elif line == 'ID_BUS=usb' or line == 'ID_BUS=ieee1394':
            removable_bus = True

    if devpath is not None:
        if is_partition:
            devpath = os.path.dirname(devpath)
        is_removable = removable_bus
        try:
            with open('/sys%s/removable' % devpath) as removable:
                if removable.readline().strip() != '0':
                    is_removable = True
        except IOError:
            pass
        if is_removable:
            try:
                subp = subprocess.Popen(['udevadm', 'info', '-q', 'name',
                                         '-p', devpath],
                                        stdout=subprocess.PIPE,
                                        universal_newlines=True)
                return ('/dev/%s' %
                        subp.communicate()[0].splitlines()[0].strip())
            except Exception:
                pass

    return None


def mount_info(path):
    """Return filesystem name, type, and ro/rw for a given mountpoint."""
    fsname = ''
    fstype = ''
    writable = ''
    with open('/proc/mounts') as fp:
        for line in fp:
            line = line.split()
            if line[1] == path:
                fsname = line[0]
                fstype = line[2]
                writable = line[3].split(',')[0]
    return fsname, fstype, writable


def udevadm_info(args):
    fullargs = ['udevadm', 'info', '-q', 'property']
    fullargs.extend(args)
    udevadm = {}
    subp = subprocess.Popen(
        fullargs, stdout=subprocess.PIPE, universal_newlines=True)
    for line in subp.communicate()[0].splitlines():
        line = line.strip()
        if '=' not in line:
            continue
        name, value = line.split('=', 1)
        udevadm[name] = value
    return udevadm


def partition_to_disk(partition):
    """Convert a partition device to its disk device, if any."""
    udevadm_part = udevadm_info(['-n', partition])
    if ('DEVPATH' not in udevadm_part or
            udevadm_part.get('DEVTYPE') != 'partition'):
        return partition

    disk_syspath = '/sys%s' % udevadm_part['DEVPATH'].rsplit('/', 1)[0]
    udevadm_disk = udevadm_info(['-p', disk_syspath])
    return udevadm_disk.get('DEVNAME', partition)


def is_boot_device_removable(boot=None):
    if boot:
        return is_removable(boot)
    else:
        return is_removable(boot_device())


def cdrom_mount_info():
    """Return mount information for /cdrom.

    This is the same as mount_info, except that the partition is converted to
    its containing disk, and we don't care whether the mount point is
    writable.
    """
    cdsrc, cdfs, _ = mount_info('/cdrom')
    cdsrc = partition_to_disk(cdsrc)
    return cdsrc, cdfs


@raise_privileges
def grub_device_map():
    """Return the contents of the default GRUB device map."""
    subp = subprocess.Popen(['grub-mkdevicemap', '--no-floppy', '-m', '-'],
                            stdout=subprocess.PIPE, universal_newlines=True)
    return subp.communicate()[0].splitlines()


def grub_default(boot=None):
    """Return the default GRUB installation target."""

    # Much of this is intentionally duplicated from grub-installer, so that
    # we can show the user what device GRUB will be installed to before
    # grub-installer is run.  Pursuant to that, we intentionally run this in
    # the installer root as /target might not yet be available.

    bootremovable = is_boot_device_removable(boot=boot)
    if bootremovable is not None:
        return bootremovable

    devices = grub_device_map()
    target = None
    if devices:
        try:
            target = os.path.realpath(devices[0].split('\t')[1])
        except (IndexError, OSError):
            pass
    # last resort
    if target is None:
        target = '(hd0)'

    cdsrc, cdfs = cdrom_mount_info()
    try:
        # The target is usually under /dev/disk/by-id/, so string equality
        # is insufficient.
        same = os.path.samefile(cdsrc, target)
    except OSError:
        same = False
    if ((same or target == '(hd0)') and
            ((cdfs and cdfs != 'iso9660') or is_removable(cdsrc))):
        # Installing from removable media other than a CD.  Make sure that
        # we don't accidentally install GRUB to it.
        boot = boot_device()
        try:
            if boot:
                target = boot
            else:
                # Try the next disk along (which can't also be the CD source).
                target = os.path.realpath(devices[1].split('\t')[1])
            # Match the more specific patterns first, then move on to the more
            # generic /dev/[a-z]+.
            target = re.sub(r'(\
                            /dev/(cciss|ida)/c[0-9]d[0-9]|\
                            /dev/nvme[0-9]+n[0-9]+|\
                            /dev/[a-z]+\
                            ).*', r'\1', target)
        except (IndexError, OSError):
            pass

    return target


_os_prober_oslist = {}
_os_prober_osvers = {}
_os_prober_called = False


def find_in_os_prober(device, with_version=False):
    """Look for the device name in the output of os-prober.

    Return the friendly name of the device, or the empty string on error.
    """
    try:
        oslist, osvers = os_prober()
        if device in oslist:
            ret = oslist[device]
        elif is_swap(device):
            ret = 'swap'
        else:
            syslog.syslog('Device %s not found in os-prober output' % device)
            ret = ''
        ret = utf8(ret, errors='replace')
        ver = utf8(osvers.get(device, ''), errors='replace')
        if with_version:
            return ret, ver
        else:
            return ret
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        import traceback
        syslog.syslog(syslog.LOG_ERR, "Error in find_in_os_prober:")
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
    return ''


@raise_privileges
def os_prober():
    global _os_prober_oslist
    global _os_prober_osvers
    global _os_prober_called

    if not _os_prober_called:
        _os_prober_called = True
        subp = subprocess.Popen(
            ['os-prober'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        result = subp.communicate()[0].splitlines()
        for res in result:
            res = res.split(':')
            # launchpad bug #1265192, fix os-prober Windows EFI path
            res[0] = re.match(r'[/\w\d]+', res[0]).group()
            if res[2] == 'Ubuntu':
                version = [v for v in re.findall('[0-9.]*', res[1]) if v][0]
                # Get rid of the superfluous (development version) (11.04)
                text = re.sub('\s*\(.*\).*', '', res[1])
                _os_prober_oslist[res[0]] = text
                _os_prober_osvers[res[0]] = version
            else:
                # Get rid of the bootloader indication. It's not relevant here.
                _os_prober_oslist[res[0]] = res[1].replace(' (loader)', '')
    return _os_prober_oslist, _os_prober_osvers


@raise_privileges
def remove_os_prober_cache():
    osextras.unlink_force('/var/lib/ubiquity/os-prober-cache')
    shutil.rmtree('/var/lib/ubiquity/linux-boot-prober-cache',
                  ignore_errors=True)


def windows_startup_folder(mount_path):
    locations = [
        # Windows 8
        'ProgramData/Microsoft/Windows/Start Menu/Programs/StartUp',
        # Windows 7
        'ProgramData/Microsoft/Windows/Start Menu/Programs/Startup',
        # Windows XP
        'Documents and Settings/All Users/Start Menu/Programs/Startup',
        # Windows NT
        'Winnt/Profiles/All Users/Start Menu/Programs/Startup',
    ]
    for location in locations:
        path = os.path.join(mount_path, location)
        if os.path.exists(path):
            return path
    return ''


ReleaseInfo = namedtuple('ReleaseInfo', 'name, version')


def get_release():
    if get_release.release_info is None:
        try:
            with open('/cdrom/.disk/info') as fp:
                line = fp.readline()
                if line:
                    line = line.split()
                    if line[2] == 'LTS':
                        line[1] += ' LTS'
                    line[0] = line[0].replace('-', ' ')
                    get_release.release_info = ReleaseInfo(
                        name=line[0], version=line[1])
        except Exception:
            syslog.syslog(syslog.LOG_ERR, 'Unable to determine the release.')

        if not get_release.release_info:
            get_release.release_info = ReleaseInfo(name='Ubuntu', version='')
    return get_release.release_info


get_release.release_info = None


def get_release_name():
    import warnings
    warnings.warn('get_release_name() is deprecated, '
                  'use get_release().name instead.',
                  category=DeprecationWarning)

    if not get_release_name.release_name:
        try:
            with open('/cdrom/.disk/info') as fp:
                line = fp.readline()
                if line:
                    line = line.split()
                    if line[2] == 'LTS':
                        get_release_name.release_name = ' '.join(line[:3])
                    else:
                        get_release_name.release_name = ' '.join(line[:2])
        except Exception:
            syslog.syslog(
                syslog.LOG_ERR,
                "Unable to determine the distribution name from "
                "/cdrom/.disk/info")
        if not get_release_name.release_name:
            get_release_name.release_name = 'Ubuntu'
    return get_release_name.release_name


get_release_name.release_name = ''


@raise_privileges
def get_install_medium():
    if not get_install_medium.medium:
        try:
            if os.access('/cdrom', os.W_OK):
                get_install_medium.medium = 'USB'
            else:
                get_install_medium.medium = 'CD'
        except Exception:
            syslog.syslog(
                syslog.LOG_ERR, "Unable to determine install medium.")
            get_install_medium.medium = 'CD'
    return get_install_medium.medium


get_install_medium.medium = ''


def execute(*args):
    """runs args* in shell mode. Output status is taken."""

    log_args = ['log-output', '-t', 'ubiquity']
    log_args.extend(args)

    try:
        status = subprocess.call(log_args)
    except IOError as e:
        syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
        syslog.syslog(syslog.LOG_ERR,
                      "OS error(%s): %s" % (e.errno, e.strerror))
        return False
    else:
        if status != 0:
            syslog.syslog(syslog.LOG_ERR, ' '.join(log_args))
            return False
        syslog.syslog(' '.join(log_args))
        return True


@raise_privileges
def execute_root(*args):
    return execute(*args)


def format_size(size):
    """Format a partition size."""
    if size < 1000:
        unit = 'B'
        factor = 1
    elif size < 1000 * 1000:
        unit = 'kB'
        factor = 1000
    elif size < 1000 * 1000 * 1000:
        unit = 'MB'
        factor = 1000 * 1000
    elif size < 1000 * 1000 * 1000 * 1000:
        unit = 'GB'
        factor = 1000 * 1000 * 1000
    else:
        unit = 'TB'
        factor = 1000 * 1000 * 1000 * 1000
    return '%.1f %s' % (float(size) / factor, unit)


def debconf_escape(text):
    escaped = text.replace('\\', '\\\\').replace('\n', '\\n')
    return re.sub(r'(\s)', r'\\\1', escaped)


def create_bool(text):
    if text == 'true':
        return True
    elif text == 'false':
        return False
    else:
        return text


@raise_privileges
def dmimodel():
    model = ''
    kwargs = {}
    if os.geteuid() != 0:
        # Silence annoying warnings during the test suite.
        kwargs['stderr'] = open('/dev/null', 'w')
    try:
        proc = subprocess.Popen(
            ['dmidecode', '--quiet', '--string', 'system-manufacturer'],
            stdout=subprocess.PIPE, universal_newlines=True, **kwargs)
        manufacturer = proc.communicate()[0]
        if not manufacturer:
            return
        manufacturer = manufacturer.lower()
        if 'to be filled' in manufacturer:
            # Don't bother with products in development.
            return
        if 'bochs' in manufacturer or 'vmware' in manufacturer:
            model = 'virtual machine'
            # VirtualBox sets an appropriate system-product-name.
        else:
            if 'lenovo' in manufacturer or 'ibm' in manufacturer:
                key = 'system-version'
            else:
                key = 'system-product-name'
            proc = subprocess.Popen(
                ['dmidecode', '--quiet', '--string', key],
                stdout=subprocess.PIPE,
                universal_newlines=True)
            model = proc.communicate()[0]
        if 'apple' in manufacturer:
            # MacBook4,1 - strip the 4,1
            model = re.sub('[^a-zA-Z\s]', '', model)
        # Replace each gap of non-alphanumeric characters with a dash.
        # Ensure the resulting string does not begin or end with a dash.
        model = re.sub('[^a-zA-Z0-9]+', '-', model).rstrip('-').lstrip('-')
        if model.lower() == 'not-available':
            return
        if model.lower() == "To be filled by O.E.M.".lower():
            return
    except Exception:
        syslog.syslog(syslog.LOG_ERR, 'Unable to determine the model from DMI')
    finally:
        if 'stderr' in kwargs:
            kwargs['stderr'].close()
    return model


def set_indicator_keymaps(lang):
    import xml.etree.cElementTree as ElementTree
    from gi.repository import Xkl, GdkX11
    # GdkX11.x11_get_default_xdisplay() segfaults if Gtk hasn't been
    # imported; possibly finer-grained than this, but anything using this
    # will already have imported Gtk anyway ...
    from gi.repository import Gtk
    from ubiquity import gsettings

    # pacify pyflakes
    Gtk

    gsettings_key = ['org.gnome.libgnomekbd.keyboard', 'layouts']
    lang = lang.split('_')[0]
    variants = []

    # Map inspired from that of gfxboot-theme-ubuntu that's itself
    # based on console-setup's. This one has been restricted to
    # language => keyboard layout not locale => keyboard layout as
    # we don't actually know the exact locale
    default_keymap = {
        'ar': 'ara',
        'bs': 'ba',
        'de': 'de',
        'el': 'gr',
        'en': 'us',
        'eo': 'epo',
        'fr': 'fr_oss',
        'gu': 'in_guj',
        'hi': 'in',
        'hr': 'hr',
        'hy': 'am',
        'ka': 'ge',
        'kn': 'in_kan',
        'lo': 'la',
        'ml': 'in_mal',
        'pa': 'in_guru',
        'sr': 'rs',
        'sv': 'se',
        'ta': 'in_tam',
        'te': 'in_tel',
        'zh': 'cn',
    }

    def item_str(s):
        '''Convert a zero-terminated byte array to a proper str'''
        import array
        s = array.array('B', s).tostring()
        i = s.find(b'\x00')
        return s[:i].decode()

    def process_variant(*args):
        if hasattr(args[2], 'name'):
            variants.append(
                '%s\t%s' % (item_str(args[1].name), item_str(args[2].name)))
        else:
            variants.append(item_str(args[1].name))

    def restrict_list(variants):
        new_variants = []

        # Start by looking by an explicit default layout in the keymap
        if lang in default_keymap:
            if default_keymap[lang] in variants:
                variants.remove(default_keymap[lang])
                new_variants.append(default_keymap[lang])
            else:
                tab_keymap = default_keymap[lang].replace('_', '\t')
                if tab_keymap in variants:
                    variants.remove(tab_keymap)
                    new_variants.append(tab_keymap)

        # Prioritize the layout matching the language (if any)
        if lang in variants:
            variants.remove(lang)
            new_variants.append(lang)

        # Uniquify our list (just in case)
        variants = list(set(variants))

        if len(variants) > 4:
            # We have a problem, X only supports 4

            # Add as many entry as we can that are layouts without variant
            country_variants = sorted(
                entry for entry in variants if '\t' not in entry)
            for entry in country_variants[:4 - len(new_variants)]:
                new_variants.append(entry)
                variants.remove(entry)

            if len(new_variants) < 4:
                # We can add some more
                simple_variants = sorted(
                    entry for entry in variants if '_' not in entry)
                for entry in simple_variants[:4 - len(new_variants)]:
                    new_variants.append(entry)
                    variants.remove(entry)

            if len(new_variants) < 4:
                # Now just add anything left
                for entry in variants[:4 - len(new_variants)]:
                    new_variants.append(entry)
                    variants.remove(entry)
        else:
            new_variants += list(variants)

        # gsettings doesn't understand utf8
        new_variants = [str(variant) for variant in new_variants]

        return new_variants

    def call_setxkbmap(variants):
        kb_layouts = []
        kb_variants = []

        for entry in variants:
            fields = entry.split('\t')
            if len(fields) > 1:
                kb_layouts.append(fields[0])
                kb_variants.append(fields[1])
            else:
                kb_layouts.append(fields[0])
                kb_variants.append("")

        execute(
            "setxkbmap", "-layout", ",".join(kb_layouts),
            "-variant", ",".join(kb_variants))

    iso_639 = ElementTree.parse('/usr/share/xml/iso-codes/iso_639.xml')
    nodes = [element for element in iso_639.findall('iso_639_entry')
             if element.get('iso_639_1_code') == lang]
    display = GdkX11.x11_get_default_xdisplay()
    engine = Xkl.Engine.get_instance(display)
    if nodes:
        configreg = Xkl.ConfigRegistry.get_instance(engine)
        configreg.load(False)

        # Apparently iso_639_2B_code doesn't always work (fails with French)
        for prop in ('iso_639_2B_code', 'iso_639_2T_code', 'iso_639_1_code'):
            code = nodes[0].get(prop)
            if code is not None:
                configreg.foreach_language_variant(code, process_variant, None)
                if variants:
                    restricted_variants = restrict_list(variants)
                    call_setxkbmap(restricted_variants)
                    gsettings.set_list(
                        gsettings_key[0], gsettings_key[1],
                        restricted_variants)
                    break
        else:
            # Use the system default if no other keymaps can be determined.
            gsettings.set_list(gsettings_key[0], gsettings_key[1], [])

    engine.lock_group(0)


NM = 'org.freedesktop.NetworkManager'
NM_STATE_CONNECTED_GLOBAL = 70


def get_prop(obj, iface, prop):
    import dbus
    try:
        return obj.Get(iface, prop, dbus_interface=dbus.PROPERTIES_IFACE)
    except dbus.DBusException as e:
        if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownMethod':
            return None
        else:
            raise


def has_connection():
    import dbus
    bus = dbus.SystemBus()
    manager = bus.get_object(NM, '/org/freedesktop/NetworkManager')
    state = get_prop(manager, NM, 'State')
    return state == NM_STATE_CONNECTED_GLOBAL


def add_connection_watch(func):
    import dbus

    def connection_cb(state):
        func(state == NM_STATE_CONNECTED_GLOBAL)

    bus = dbus.SystemBus()
    bus.add_signal_receiver(connection_cb, 'StateChanged', NM, NM)
    try:
        func(has_connection())
    except dbus.DBusException:
        # We can't talk to NM, so no idea.  Wild guess: we're connected
        # using ssh with X forwarding, and are therefore connected.  This
        # allows us to proceed with a minimum of complaint.
        func(True)


def install_size():
    if min_install_size:
        return min_install_size

    # Fallback size to 5 GB
    size = 5 * 1024 * 1024 * 1024

    # Maximal size to 8 GB
    max_size = 8 * 1024 * 1024 * 1024

    try:
        with open('/cdrom/casper/filesystem.size') as fp:
            size = int(fp.readline())
    except IOError:
        pass

    # TODO substitute into the template for the state box.
    min_disk_size = size * 2  # fudge factor

    # Set minimum size to 8GB if current minimum size is larger
    # than 8GB and we still have an extra 20% of free space
    if min_disk_size > max_size and size * 1.2 < max_size:
        min_disk_size = max_size

    return min_disk_size


min_install_size = None

# vim:ai:et:sts=4:tw=80:sw=4:
