import unittest
from unittest.mock import patch
from admin_app import provider_key_present

class ConfigMetadataTests(unittest.TestCase):
    def test_present_and_absent_names_only(self):
        self.assertTrue(provider_key_present(['OTHER','FAL_KEY']))
        self.assertFalse(provider_key_present(['OTHER','FAL_API_KEY']))
    def test_never_reads_environment_value(self):
        class NamesOnly:
            def keys(self):return ['FAL_KEY']
            def __getitem__(self,key):raise AssertionError('Secret value must not be read')
        with patch('admin_app.os.environ',NamesOnly()):self.assertTrue(provider_key_present())
