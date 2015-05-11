#!/bin/bash
rm -rf /var/cache/libvirt/qemu/capabilities
systemctl restart libvirtd.service
