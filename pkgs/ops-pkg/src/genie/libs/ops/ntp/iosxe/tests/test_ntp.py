# Python
import unittest
from copy import deepcopy
from unittest.mock import Mock

# ATS
from ats.topology import Device

# Genie
from genie.libs.ops.ntp.iosxe.ntp import Ntp
from genie.libs.ops.ntp.iosxe.tests.ntp_output import NtpOutput,\
                                                      NtpOutputNoConfig

# Parser
from genie.libs.parser.iosxe.show_ntp import ShowNtpAssociations, \
                                             ShowNtpStatus, \
                                             ShowNtpConfig

# Set values
outputs = {}
outputs['show ntp associations'] = NtpOutputNoConfig.ShowNtpAssociations
outputs['show ntp status'] = NtpOutputNoConfig.ShowNtpStatus
outputs['show ntp config'] = NtpOutputNoConfig.ShowNtpConfig

def mapper(key):
    return outputs[key]


class test_ntp(unittest.TestCase):

    def setUp(self):
        self.device = Device(name='aDevice')
        self.device.os = 'iosxe'
        self.device.mapping={}
        self.device.mapping['cli']='cli'
        # Give the device as a connection type
        # This is done in order to call the parser on the output provided
        self.device.connectionmgr.connections['cli'] = self.device

    def test_complete_output(self):
        self.maxDiff = None
        ntp = Ntp(device=self.device)
        # Get outputs
        ntp.maker.outputs[ShowNtpAssociations] = \
            {"": NtpOutput.ShowNtpAssociations}

        ntp.maker.outputs[ShowNtpStatus] = \
            {"": NtpOutput.ShowNtpStatus}

        ntp.maker.outputs[ShowNtpConfig] = \
            {"": NtpOutput.ShowNtpConfig}

        # Learn the feature
        ntp.learn()

        # Verify Ops was created successfully
        self.assertEqual(ntp.info, NtpOutput.Ntp_info)

        # Check specific attribute values
        # info - default vrf
        self.assertEqual(ntp.info['clock_state']['system_status']['clock_state'], 'synchronized')
        # info - vrf VRF1
        self.assertEqual(ntp.info['vrf']['VRF1']['unicast_configuration']['address']\
                                 ['10.64.4.4']['type']['server']['type'], 'server')

    def test_empty_output(self):
        self.maxDiff = None
        ntp = Ntp(device=self.device)
        # Get outputs
        ntp.maker.outputs[ShowNtpAssociations] = \
            {"": {}}

        ntp.maker.outputs[ShowNtpStatus] = \
            {"": {}}

        ntp.maker.outputs[ShowNtpConfig] = \
            {"": {}}

        # Learn the feature
        ntp.learn()

        # Check no attribute not found
        with self.assertRaises(AttributeError):
            ntp.info['clock_state']

    def test_incomplete_output(self):
        self.maxDiff = None
        
        ntp = Ntp(device=self.device)

        # Get outputs
        ntp.maker.outputs[ShowNtpAssociations] = \
            {"": NtpOutput.ShowNtpAssociations}

        ntp.maker.outputs[ShowNtpStatus] = \
            {"": {}}

        ntp.maker.outputs[ShowNtpConfig] = \
            {"": NtpOutput.ShowNtpConfig}

        # Learn the feature
        ntp.learn()
                
        # Check no attribute not found
        with self.assertRaises(KeyError):
            ntp.info['clock_state']['system_status']['actual_freq']
            ntp.info['clock_state']['system_status']['clock_precision']
            ntp.info['clock_state']['system_status']['reference_time']
            ntp.info['clock_state']['system_status']['root_dispersion']

class test_ntp_without_peer_configuration(unittest.TestCase):
    '''only has ntp default configured on device'''

    def setUp(self):
        self.device = Device(name='aDevice')
        self.device.os = 'nxos'
        self.device.mapping={}
        self.device.mapping['cli']='cli'
        # Give the device as a connection type
        # This is done in order to call the parser on the output provided
        self.device.connectionmgr.connections['cli'] = self.device

    def test_complete_output(self):
        self.maxDiff = None
        ntp = Ntp(device=self.device)
        
        # Return outputs above as inputs to parser when called
        self.device.execute = Mock()
        self.device.execute.side_effect = mapper

        # Learn the feature
        ntp.learn()

        # Verify Ops was created successfully
        self.assertEqual(ntp.info, NtpOutputNoConfig.Ntp_info)

        # Check specific attribute values
        # info - default vrf
        self.assertEqual(ntp.info['clock_state']['system_status']\
            ['associations_address'], '127.127.1.1')


if __name__ == '__main__':
    unittest.main()
