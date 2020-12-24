#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

import os
import commands
import argparse
import sys
import getpass
import platform
import logging

from .utils import LagoUserException

LOGGER = logging.getLogger(__name__)

class VerifyLagoStatus(object):
    """
    Verify Lago configuration
    """
    verificationStatus = False
    def __init__(self,username,envs_dir,config_dict,verify_status):
        self.username = username
        self.envs_dir = envs_dir
        self.groups = config_dict['groups']
        self.nested = config_dict['nested']
        self.virtualization = config_dict['virtualization']
        self.lago_env_dir = config_dict['lago_env_dir']
        self.kvm_configure = config_dict['kvm_configure']
        self.install_pkg = config_dict['install_pkg']
        self.home_permissions = config_dict['home_permissions']
        self.ipv6_networking = config_dict['ipv6_networking']
        VerifyLagoStatus.verificationStatus = verify_status

    def displayLagoStatus(self,display_list):
        """
        Display Lago configuration status (OK/Not-OK) Verify Lago configuration
        """
        if (display_list):
            print "Configuration Status:"
            print "====================="
            print "Username used by Lago: " + self.username
            print "Environment directory used by Lago: " + self.envs_dir 
            print "Nested: " + self.return_status(self.nested)
            print "Virtualization: " +  self.return_status(self.virtualization)
            print "Groups: " + self.return_status(self.groups)
            print "Lago Environment Directory " +  self.envs_dir + ": " + self.return_status(self.lago_env_dir)
            print "Kvm Configure: " +  self.return_status(self.kvm_configure)
            print "All packages installed: " +  self.return_status(self.install_pkg)
            print "Home Directory permissions: " +  self.return_status(self.home_permissions)
            print "IPV6 configure: " +  self.return_status(self.ipv6_networking)
            print "Status: " + str(VerifyLagoStatus.verificationStatus)

        if (VerifyLagoStatus.verificationStatus == False):
            print "Please read configuration setup:"
            print "  http://lago.readthedocs.io/en/latest/Installation.html#troubleshooting"
            return 2
        else: 
            return 0    
        
    def fixLagoConfiguration(self,config_dict,verify_status):
        """
        Fix Lago configuration if possible
        """
        self.groups = config_dict['groups']
        self.nested = config_dict['nested']
        self.virtualization = config_dict['virtualization']
        self.lago_env_dir = config_dict['lago_env_dir']
        self.kvm_configure = config_dict['kvm_configure']
        self.install_pkg = config_dict['install_pkg']
        self.home_permissions = config_dict['home_permissions']
        self.ipv6_networking = config_dict['ipv6_networking']
        VerifyLagoStatus.verificationStatus = verify_status

    def return_status(self,status):
        """
        Display OK or Not-OK
        """
        if status == 'Y':
            return "OK"
        else:
            return "Not-OK"    

def validate_status(list_status):
    """
    Validate the status of all configuration checks
    """
    status = True
    list_not_configure=[]
    if 'N' in list_status.itervalues():
        status = False
        list_not_configure = [k for k,v in list_status.iteritems() if v == 'N']
    return status,list_not_configure    

def check_virtualization():
    """
    Check if KVM configure in BIOS
    """    
    if os.system("dmesg | grep -q 'kvm: disabled by BIOS'"):
      virtualization =  'N'
    else:
      virtualization =  'Y'
    return virtualization

def get_cpu_vendor():
    """
    Get the CPU vendor ie. intel/amd
    """ 
    (exit_code,Input ) = exec_cmd("lscpu | awk '/Vendor ID/{print $3}'")
    if Input == 'GenuineIntel': 
        vendor = "intel"
    elif vendor == 'AuthenticAMD':
        vendor = "amd"
    else:
        vendor = "problem"
    return vendor

def is_virtualization_enable():
    """
    Check if Virtualization enabled
    """ 
    (exit_code,res) = exec_cmd("cat /proc/cpuinfo | egrep 'vmx|svm'")
  
    if res == "": 
        status = "N"
    else:
        status = "Y"
    return status

def check_kvm_configure(vendor):
    """
    Check if KVM configure
    """ 
    cmd = "lsmod | grep kvm_"+vendor
    (exit_code,res) = exec_cmd("lsmod | grep kvm_"+vendor)

    if res == "": 
        status = "N"
    else:
        status = "Y"
    return status

def check_nested(vendor):
    """
    Check if nested is available
    """ 
    mod="kvm_"+vendor
    cmd = "cat /sys/module/"+mod+"/parameters/nested"
    (exit_code,is_enabled) = exec_cmd(cmd)
    if is_enabled == 'Y':
        return 'Y'
    else: 
        return 'N'

def check_groups(username):
    """
    Check the groups are confiugre correct for LAGO
    """ 
    ## all groups username in
    cmd = "groups " + username
    (exit_code,groups_username) = exec_cmd(cmd)
    status_username = all(x in groups_username for x in ['qemu','libvirt','lago',username])
    cmd = "groups qemu"
    (exit_code,groups_qemu) = exec_cmd(cmd)
    status_qemu = all(x in groups_qemu for x in [username])
    if ( status_username &  status_qemu ):
        return 'Y'
    else: 
        return 'N'

def change_groups(username):
    """
    Update the groups according to LAGO permissions
    """ 
    exec_cmd("usermod -a -G qemu,libvirt,lago " + username) 
    exec_cmd("usermod -a -G " + username + " qemu") 

def check_home_dir_permmisions():
    import stat
    _USERNAME = os.getenv("SUDO_USER") or os.getenv("USER") 
    _HOME = os.path.expanduser('~'+_USERNAME)
    mode = os.stat(_HOME).st_mode
    group_exe = (stat.S_IMODE(mode) &  stat.S_IXGRP !=  stat.S_IXGRP)
    if group_exe:
        return "N"
    else: 
        return "Y"    
 
def change_home_dir_permissions():
    _USERNAME = os.getenv("SUDO_USER") or os.getenv("USER") 
    _HOME = os.path.expanduser('~'+_USERNAME)
    exec_cmd("chmod g+x " +  _HOME) 
 
def remove_write_permissions(path):
    """Remove write permissions from this path, while keeping all other permissions intact.

    Params:
        path:  The path whose permissions to alter.
    """
    NO_USER_WRITING = ~stat.S_IWUSR
    NO_GROUP_WRITING = ~stat.S_IWGRP
    NO_OTHER_WRITING = ~stat.S_IWOTH
    NO_WRITING = NO_USER_WRITING & NO_GROUP_WRITING & NO_OTHER_WRITING
    current_permissions = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, current_permissions & NO_WRITING)

def check_permissions(envs_dirs,username):
    """
    Check directory permissions
    """ 
    status = True
    (exit_code,uid) = exec_cmd("id -u  " + username)
    (exit_code,gid) = exec_cmd("getent group  " + username + " | awk -F: '{print $3}'")
    for dirpath, dirnames, filenames in os.walk(envs_dirs):  
        if ( os.stat(dirpath).st_uid != int(uid) ) &  (os.stat(dirpath).st_gid != int(gid)):
            status = False 
        for dirname in dirnames:  
            if ( os.stat(os.path.join(dirpath, dirname)).st_uid != int(uid) ) &  (os.stat(os.path.join(dirpath, dirname)).st_gid != int(gid)):
                status = False
        for filename in filenames:
            if ( os.stat(os.path.join(dirpath, filename)).st_uid != int(uid) ) &  (os.stat(os.path.join(dirpath, filename)).st_gid != int(gid)):
                status = False
    if ( status ):
        return 'Y'
    else: 
        return 'N'

def change_permissions(envs_dirs,username):
    """
    Change directory permissions
    """ 
    (exit_code,uid) = exec_cmd("id -u  " + username)
    (exit_code,gid) = exec_cmd("getent group  " + username + " | awk -F: '{print $3}'")
    for dirpath, dirnames, filenames in os.walk(envs_dirs):  
        os.chown(dirpath, int(uid), int(gid))
        for dirname in dirnames:  
            os.chown(os.path.join(dirpath, dirname), int(uid), int(gid))
        for filename in filenames:
            os.chown(os.path.join(dirpath, filename), int(uid), int(gid))
 
def check_packages_installed():
    """
    Check if all required packages are installed
    """ 
    missing_pkg = []
    status = "Y"
    if  platform.linux_distribution()[0] == "CentOS Linux":
        pkg_list = ["epel-release", "centos-release-qemu-ev", "python-devel", "libvirt", "libvirt-devel" , "libguestfs-tools", "libguestfs-devel", "gcc", "libffi-devel", "openssl-devel", "qemu-kvm-ev"]
    else:
        pkg_list = ["python2-devel", "libvirt", "libvirt-devel" , "libguestfs-tools", "libguestfs-devel", "gcc", "libffi-devel", "openssl-devel", "qemu-kvm"]
    (exit_code,rpm_output) = exec_cmd("rpm -qa ")

    for pkg in pkg_list:        
        if pkg not in rpm_output:
            missing_pkg.append(pkg)  
            status =  'N'
    return (status,missing_pkg)

def install_missing_packages(missing_pkg):
    """
    Install missing packages
    """ 
    for pkg in missing_pkg:     
        (exit_code,res)=exec_cmd("yum install -y " + pkg) 

def enable_nested(vendor):
    filename = "/etc/modprobe.d/kvm-" + vendor + ".conf"
    line_to_write="options kvm-" + vendor + " nested=y"
    with open(filename, 'r') as content_file:
        content = content_file.read()
    if line_to_write not in  content:
        file = open(filename,"a") 
        file.write("options kvm-" + vendor + " nested=y" ) 
        file.close() 

def reload_kvm(vendor):
    """
    reload kvm
    """    
    mod = "kvm-" + vendor
    (exit_code,output) = exec_cmd("modprobe -r " + mod + " ; modprobe -r kvm ; modprobe kvm ; modprobe " + mod )

def enable_service(service):
    """
    enable service
    """
    exec_cmd("systemctl enable " + service + "; systemctl restart " + service  )

def check_configure_ipv6_networking():
    with open('/etc/sysctl.conf', 'r') as content_file:
        content = content_file.read()
    if "net.ipv6.conf.all.accept_ra=2" in  content:
        return 'Y'
    else:
        return 'N'
    
def configure_ipv6_networking():
    file = open("/etc/sysctl.conf","a") 
    file.write("net.ipv6.conf.all.accept_ra=2" ) 
    file.close() 
    print exec_cmd("sysctl -p")

def check_user(username):
    """
    Check if user exists in passwd
    """ 
    msg=""
    (exit_code,uid) = exec_cmd("id -u  " + username)

    if "no such user" in uid: 
        msg = "\'"+username+"\'"+ " username doesn't exists"
    return msg
        
def check_directory(envs_dir):
    """
    Check if directory exists
    """ 
    msg=""
    if (os.path.isdir(envs_dir)==False):
        msg = "\'"+envs_dir+"\'"+ " envs_dir doesn't exists"
    return msg    

def check_configuration(username,envs_dir):
    """
    Check the configuration of LAGO (what is configure)
    """ 
    config_dict={}
    config_dict['vendor'] = get_cpu_vendor()
    config_dict['nested'] = check_nested(config_dict['vendor'])
    #virtualization = check_virtualization()
    config_dict['virtualization'] = is_virtualization_enable()
    config_dict['groups'] = check_groups(username)
    config_dict['lago_env_dir'] = check_permissions(envs_dir,username)
    config_dict['kvm_configure'] = check_kvm_configure(config_dict['vendor'])
    (config_dict['install_pkg'],missing_pkg) = check_packages_installed()
    config_dict['home_permissions'] = check_home_dir_permmisions()
    config_dict['ipv6_networking'] = check_configure_ipv6_networking()
    return config_dict
    
def fix_configuration(username,envs_dir,config_dict):
    """
    Fix configuration, if possible
    - file permissions
    - groups
    - packages
    - nested
    - kvm virtualization
    """ 
    if (config_dict['lago_env_dir'] == 'N'):
        change_permissions(envs_dir,username)

    if (config_dict['groups'] == 'N'):
        change_groups(username)

    if (config_dict['install_pkg'] == 'N'):
        (install_pkg,missing_pkg) = check_packages_installed()
        install_missing_packages(missing_pkg) 

    if (config_dict['home_permissions'] == 'N'):
        change_home_dir_permissions() 

    if (config_dict['ipv6_networking'] == 'N'):
        configure_ipv6_networking()

    vendor = get_cpu_vendor()
    if (config_dict['nested'] == 'N'):
        enable_nested(vendor)
        reload_kvm(vendor)

    enable_service("libvirtd")    

def exec_cmd(cmd):
    """
    Execute the requested command and return list with the cmd exit code and the output written to stdout/stderr.  
    """
    (exit_code,output)= commands.getstatusoutput(cmd)
    if (exit_code == 0):
        LOGGER.debug("Running command '%s' succeeded", cmd)
    else:
        LOGGER.debug("Running command '%s' failed", cmd)    
    #print "Exit code:" + str(exit_code)
    #print "Exit code:" + str(output) 
    return exit_code,output