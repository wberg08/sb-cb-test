# pylint: disable=invalid-name, no-self-use
# This test file should be executable from any directory
# Follow the comment below when importing any modules you create

import os
import sys
import unittest
from unittest import mock

script_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, script_path + '/..')

# Add any imports that test your function code below here

import token_replacer  # nopep8 pylint: disable=wrong-import-position


class TestTokenReplacer(unittest.TestCase):

    @mock.patch('token_replacer.os.walk')
    def test_has_duplicates_returns_false(self, mock_os_walk):
        # test single folder
        mock_os_walk.return_value = [(
            'folder/path',
            ['subfolder1'],
            ['file1.sh', 'file2.yaml', 'file3.template']
        )]
        result = token_replacer.has_duplicates('folder/to/traverse')
        self.assertFalse(result)

        # Test 2 folders, no matching files.
        mock_os_walk.return_value = [(
            'folder/path',
            ['subfolder1'],
            ['file1.sh', 'file2.yaml', 'file3.template']
        ), (
            'another/folder/path',
            ['subfolder2'],
            ['file4.sh', 'file5.yaml', 'file6.template']
        )]
        result = token_replacer.has_duplicates('folder/to/traverse')
        self.assertFalse(result)

    @mock.patch('token_replacer.os.walk')
    def test_has_duplicates_returns_true(self, mock_os_walk):
        # Test Matching files across 2 folders.
        mock_os_walk.return_value = [(
            'folder/path',
            ['subfolder1'],
            ['file1.sh', 'file2.yaml', 'file3.template']
        ), (
            'another/folder/path',
            ['subfolder2'],
            ['file4.sh', 'file2.yaml', 'file6.template']
        )]
        result = token_replacer.has_duplicates('folder/to/traverse')
        self.assertTrue(result)

        # Test Matching files across 3 folders.
        mock_os_walk.return_value = [(
            'folder/path',
            ['subfolder1'],
            ['file1.sh', 'file2.yaml', 'file3.template']
        ), (
            'another/folder/path',
            ['subfolder2'],
            ['file1.sh', 'file5.yaml', 'file6.template']
        ), (
            'third/folder/path',
            ['subfolder2'],
            ['file7.sh', 'file8.yaml', 'file6.template']
        )]
        result = token_replacer.has_duplicates('folder/to/traverse')
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main(buffer=False)
