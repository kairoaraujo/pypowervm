# Copyright 2015 IBM Corp.
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tasks around IBMi VM changes."""

from oslo_log import log as logging

import pypowervm.exceptions as pvmex
from pypowervm import i18n
import pypowervm.tasks.scsi_mapper as pvm_smap
import pypowervm.tasks.vfc_mapper as pvm_vfcmap
import pypowervm.wrappers.base_partition as pvm_bp
import pypowervm.wrappers.logical_partition as pvm_lpar
from pypowervm.wrappers import network as pvm_net
from pypowervm.wrappers import virtual_io_server as pvm_vios

LOG = logging.getLogger(__name__)

# TODO(IBM) translation
_LI = i18n._


def update_ibmi_settings(adapter, lpar_w, boot_type):
    """Update TaggedIO, Keylock postion and IPL Source of IBMi VM.

    TaggedIO of IBMi vm will be updated to identify the load source,
    alternative load source and console type. Keylock position will be set
    to the value of NORMAL in KeylockPos enumration. IPL Source will be set
    to the value of B in IPLSrc enumration.
    :param adapter: The pypowervm adapter.
    :param lpar_w: The lpar wrapper.
    :param boot_type: The boot connectivity type of the VM. It is a string
                      value that represents one of the values in the
                      BootStorageType enumeration.
    :return: The updated LPAR wrapper. The update is not executed against the
             system, but rather the wrapper itself is updated locally.
    """
    load_source = None
    alt_load_source = None
    client_adapters = []
    console_type = 'HMC'
    # Set the console type as vea adapter if the host is not managed by HMC
    if adapter.traits.vea_as_ibmi_console:
        msg = _LI("Setting Virtual Ethernet Adapter slot as console type for "
                  "VM %s") % lpar_w.name
        LOG.info(msg)
        cna_wrap = pvm_net.CNA.wrap(adapter.read(
            pvm_lpar.LPAR.schema_type,
            root_id=lpar_w.partition_uuid,
            child_type=pvm_net.CNA.schema_type))
        cna_slot_nums = set(cna.slot for cna in cna_wrap)
        cna_slot_nums = list(cna_slot_nums)
        cna_slot_nums.sort()
        if len(cna_slot_nums) > 0:
            console_type = cna_slot_nums.pop(0)
    if boot_type == pvm_lpar.BootStorageType.VFC:
        msg = _LI("Setting Virtual Fibre Channel slot as load source for VM "
                  "%s") % lpar_w.name
        LOG.info(msg)
        vios_wraps = pvm_vios.VIOS.wrap(adapter.read(
            pvm_vios.VIOS.schema_type,
            xag=[pvm_vios.VIOS.xags.FC_MAPPING]))
        for vios_wrap in vios_wraps:
            existing_maps = pvm_vfcmap.find_maps(
                vios_wrap.vfc_mappings, lpar_w.id)
            client_adapters.extend([vfcmap.client_adapter
                                    for vfcmap in existing_maps])
    else:
        # That boot volume, which is vscsi physical volume, ssp lu
        # and local disk, could be handled here.
        msg = _LI("Setting Virtual SCSI slot slot as load source for VM "
                  "%s") % lpar_w.name
        LOG.info(msg)
        vios_wraps = pvm_vios.VIOS.wrap(adapter.read(
            pvm_vios.VIOS.schema_type,
            xag=[pvm_vios.VIOS.xags.SCSI_MAPPING]))
        for vios_wrap in vios_wraps:
            existing_maps = pvm_smap.find_maps(
                vios_wrap.scsi_mappings, lpar_w.id)
            client_adapters.extend([smap.client_adapter
                                    for smap in existing_maps])
    slot_nums = set(s.lpar_slot_num for s in client_adapters)
    slot_nums = list(slot_nums)
    slot_nums.sort()
    if len(slot_nums) > 0:
        load_source = slot_nums.pop(0)
    if len(slot_nums) > 0:
        alt_load_source = slot_nums.pop(0)
    if load_source is not None:
        if alt_load_source is None:
            alt_load_source = load_source
        lpar_w.io_config.tagged_io = pvm_bp.TaggedIO.bld(
            adapter, load_src=load_source,
            console=console_type,
            alt_load_src=alt_load_source)
    else:
        raise pvmex.IBMiLoadSourceNotFound(vm_name=lpar_w.name)
    lpar_w.desig_ipl_src = pvm_lpar.IPLSrc.B
    lpar_w.keylock_pos = pvm_bp.KeylockPos.NORMAL
    return lpar_w
