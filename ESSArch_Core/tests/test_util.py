import datetime
import os
import shutil
import sys
import tempfile
from subprocess import PIPE
from unittest import mock

from django.core.files.base import ContentFile
from django.http.response import FileResponse
from django.test import SimpleTestCase, TestCase
from lxml import etree, objectify
from rest_framework.exceptions import NotFound, ValidationError

from ESSArch_Core.util import (
    convert_file,
    delete_path,
    find_destination,
    flatten,
    generate_file_response,
    get_files_and_dirs,
    get_script_directory,
    get_value_from_path,
    getSchemas,
    list_files,
    nested_lookup,
    normalize_path,
    parse_content_range_header,
)


class ConvertFileTests(SimpleTestCase):
    @mock.patch('ESSArch_Core.util.Popen')
    def test_non_zero_returncode(self, mock_popen):
        process_mock = mock.Mock()
        attrs = {'communicate.return_value': ('output', 'error'), 'returncode': 1}
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock

        with self.assertRaises(ValueError):
            convert_file("test.docx", "pdf")

        if sys.platform == "win32":
            cmd = ['python.exe', os.path.join(get_script_directory(), 'unoconv.py')]
        else:
            cmd = ['unoconv']
        cmd.extend(['-f', 'pdf', '-eSelectPdfVersion=1', 'test.docx'])
        mock_popen.assert_called_once_with(cmd, stderr=PIPE, stdout=PIPE)

    @ mock.patch('ESSArch_Core.util.os.path.isfile', return_value=False)
    @ mock.patch('ESSArch_Core.util.Popen')
    def test_zero_returncode_with_no_file_created(self, mock_popen, mock_isfile):
        process_mock = mock.Mock()
        attrs = {'communicate.return_value': ('output', 'error'), 'returncode': 0}
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock

        with self.assertRaises(ValueError):
            convert_file("test.docx", "pdf")

        if sys.platform == "win32":
            cmd = ['python.exe', os.path.join(get_script_directory(), 'unoconv.py')]
        else:
            cmd = ['unoconv']
        cmd.extend(['-f', 'pdf', '-eSelectPdfVersion=1', 'test.docx'])
        mock_popen.assert_called_once_with(cmd, stderr=PIPE, stdout=PIPE)

    @ mock.patch('ESSArch_Core.util.os.path.isfile', return_value=True)
    @ mock.patch('ESSArch_Core.util.Popen')
    def test_zero_returncode_with_file_created(self, mock_popen, mock_isfile):
        process_mock = mock.Mock()
        attrs = {'communicate.return_value': ('output', 'error'), 'returncode': 0}
        process_mock.configure_mock(**attrs)
        mock_popen.return_value = process_mock

        self.assertEqual(convert_file("test.docx", "pdf"), 'test.pdf')

        if sys.platform == "win32":
            cmd = ['python.exe', os.path.join(get_script_directory(), 'unoconv.py')]
        else:
            cmd = ['unoconv']
        cmd.extend(['-f', 'pdf', '-eSelectPdfVersion=1', 'test.docx'])
        mock_popen.assert_called_once_with(cmd, stderr=PIPE, stdout=PIPE)


class GetValueFromPathTest(TestCase):

    @ staticmethod
    def get_simple_xml():
        return '''
                    <volym andraddat="2014-03-11T14:10:35">
                        <volnr>1</volnr>
                        <tid>2000 -- 2005</tid>
                        <utseende>utseende_text</utseende>
                        <anmerkningar>anmerkningar_text</anmerkningar>
                    </volym>
        '''

    def test_get_value_from_path_when_path_is_none(self):
        xml = self.get_simple_xml()
        root_xml = objectify.fromstring(xml)
        self.assertIsNone(get_value_from_path(root_xml, None))

    def test_get_value_from_path_when_attribute_is_missing(self):
        xml = self.get_simple_xml()
        root_xml = objectify.fromstring(xml)
        self.assertIsNone(get_value_from_path(root_xml, "anmerkningar@non_existing_attr"))


class GetFilesAndDirsTest(TestCase):

    def test_get_files_and_dirs_none_existent_dir(self):
        self.assertEqual(get_files_and_dirs("this_folder_or_path_should_not_exist"), [])


class ParseContentRangeHeaderTest(SimpleTestCase):

    def test_parse_content_range_header(self):
        header = 'bytes 123-456/789'
        ref_start = 123
        ref_end = 456
        ref_total = 789

        (start, end, total) = parse_content_range_header(header)
        self.assertEqual(start, ref_start)
        self.assertEqual(end, ref_end)
        self.assertEqual(total, ref_total)

    def test_parse_content_range_header_with_bad_header(self):
        header = "bad header"
        with self.assertRaisesRegex(ValidationError, "Invalid Content-Range header"):
            parse_content_range_header(header)


class FlattenTest(SimpleTestCase):

    def test_flatten_list_of_lists(self):
        my_list = [
            list(range(1, 10)),
            list(range(10, 20)),
        ]

        result_list = list(range(1, 20))
        self.assertEqual(result_list, flatten(my_list))


class GetSchemasTest(SimpleTestCase):

    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir)

    def get_simple_valid_xml(self):
        tmp_file = tempfile.TemporaryFile(dir=self.datadir)
        tmp_file.write(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
        tmp_file.write(b'<xml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                       b'xmlns="http://www.example.com/example/v4.2" '
                       b'xsi:schemaLocation="http://www.example.com/example/v4.2 '
                       b'http://www.example.com/example/v4.2/example.xsd"></xml>')
        tmp_file.seek(0)

        return tmp_file

    def get_bad_xml_file(self):
        tmp_file = tempfile.TemporaryFile(dir=self.datadir)
        tmp_file.write(b'Hello bad XML syntax!')
        tmp_file.seek(0)

        return tmp_file

    def test_get_schemas_from_doc(self):
        filename = self.get_simple_valid_xml()

        parser = etree.XMLParser(remove_blank_text=True)
        doc = etree.parse(filename, parser=parser)

        schema = getSchemas(doc=doc)
        self.assertIs(type(schema), etree._Element)

    def test_get_schema_from_file(self):
        schema = getSchemas(filename=self.get_simple_valid_xml())
        self.assertIs(type(schema), etree._Element)

    def test_get_schema_with_no_argument_should_throw_exception(self):
        with self.assertRaisesRegexp(AttributeError, "'NoneType' object has no attribute 'getroot'"):
            getSchemas()

    def test_get_schema_from_none_existing_file_should_raise_exception(self):
        filename = "this_file_hopefully_does_not_exist"

        with self.assertRaises(IOError):
            getSchemas(filename=filename)

    def test_get_schema_from_file_with_bad_input(self):
        fp = self.get_bad_xml_file()

        with self.assertRaises(etree.XMLSyntaxError):
            getSchemas(filename=fp)


class NestedLookupTest(TestCase):
    def test_nested_lookup_dict_first_layer(self):
        my_dict = {"my_key": 42}

        self.assertEqual(42, next(nested_lookup('my_key', my_dict)))

    def test_nested_lookup_nested_dict_two_layer(self):
        my_dict = {"first_layer": {"my_key": 42}}

        self.assertEqual(42, next(nested_lookup('my_key', my_dict)))

    def test_nested_lookup_list_in_dict(self):
        my_dict = {"first_layer": [
            {"key_1": 1},
            {"key_2": 2},
            {"my_key": 42},
            {"key_3": 3},
        ]}

        self.assertEqual(42, next(nested_lookup('my_key', my_dict)))

    def test_nested_lookup_dict_in_list(self):
        my_list = [
            {"key_1": 1},
            {"key_2": 2},
            {"my_key": 42},
            {"key_3": 3},
        ]

        self.assertEqual(42, next(nested_lookup('my_key', my_list)))

    def test_nested_lookup_multiple_occurrences_should_return_all_of_them(self):
        my_list = {
            "first_layer": [
                {"my_key": 1},
                {"key_2": 2},
                {"my_key": 3},
            ],
            "second_layer": [
                {"key_3": 3},
                {"my_key": 5},
                {"key_4": 4},
                {"my_key": 7},
            ]
        }

        found_values = list(nested_lookup('my_key', my_list))
        self.assertCountEqual([1, 3, 5, 7], found_values)

    def test_nested_lookup_key_missing_should_return_None(self):
        my_list = [
            {"key_1": 1},
            {"key_2": 2},
            {"key_3": 3},
        ]

        result_list = list(nested_lookup('missing_key', my_list))
        self.assertEqual(len(result_list), 0)


class ListFilesTest(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir)

        self.textdir = os.path.join(self.datadir, "textdir")
        os.makedirs(self.textdir)

    def create_files(self):
        files = []
        for i in range(3):
            fname = os.path.join(self.textdir, '%s.txt' % i)
            with open(fname, 'w') as f:
                f.write('%s' % i)
            files.append(fname)

        return files

    def create_archive_file(self, archive_format):
        self.create_files()

        output_filename = "archive_file"
        archive_file_full_path = os.path.join(self.datadir, output_filename)

        return shutil.make_archive(archive_file_full_path, archive_format, self.textdir)

    def test_list_files_dir_with_default_args_should_raise_NotFound(self):
        path = self.datadir
        self.create_files()

        with self.assertRaises(NotFound):
            list_files(path)

    def test_list_files_tarfile_with_default_args_should_return_response(self):
        file_path = self.create_archive_file('tar')
        resp = list_files(file_path)
        self.assertEqual(resp.status_code, 200)
        file_names = ["./0.txt", "./1.txt", "./2.txt"]  # TODO: bug in shutil for tar is adding an extra './'

        for el in resp.data:
            data_name = el['name']
            data_type = el['type']
            data_size = el['size']
            data_modified = el['modified']

            self.assertIn(data_name, file_names)
            file_names.remove(data_name)
            self.assertEqual(data_type, "file")
            self.assertEqual(data_size, 1)
            self.assertEqual(type(data_modified), datetime.datetime)

    def test_list_files_zip_file_with_default_args_should_return_response(self):
        file_path = self.create_archive_file('zip')
        resp = list_files(file_path)
        self.assertEqual(resp.status_code, 200)
        file_names = ["0.txt", "1.txt", "2.txt"]

        for el in resp.data:
            data_name = el['name']
            data_type = el['type']
            data_size = el['size']
            data_modified = el['modified']

            self.assertIn(data_name, file_names)
            file_names.remove(data_name)
            self.assertEqual(data_type, "file")
            self.assertEqual(data_size, 1)
            self.assertEqual(type(data_modified), datetime.datetime)

    @ mock.patch('ESSArch_Core.util.generate_file_response')
    def test_list_files_path_to_file_in_tar(self, generate_file_response):
        file_path = self.create_archive_file('tar')
        sub_path_file = './0.txt'  # TODO: bug in shutil for tar is adding an extra './'
        new_folder = os.path.join(file_path, sub_path_file)

        new_folder = normalize_path(new_folder)

        list_files(new_folder)

        generate_file_response.assert_called_once_with(mock.ANY, 'text/plain', False, name=sub_path_file)

    def test_list_files_path_to_non_existing_file_in_tar_should_throw_NotFound(self):
        file_path = self.create_archive_file('tar')
        new_folder = os.path.join(file_path, "non_existing_file.txt")

        with self.assertRaises(NotFound):
            list_files(new_folder)

    def test_list_files_path_to_non_existing_file_in_zip_should_throw_NotFound(self):
        file_path = self.create_archive_file('zip')
        new_folder = os.path.join(file_path, "non_existing_file.txt")

        with self.assertRaises(NotFound):
            list_files(new_folder)

    @ mock.patch('ESSArch_Core.util.generate_file_response')
    def test_list_files_path_to_file_in_zip(self, generate_file_response):
        file_path = self.create_archive_file('zip')
        sub_path_file = '0.txt'
        new_folder = os.path.join(file_path, sub_path_file)

        new_folder = normalize_path(new_folder)

        list_files(new_folder)

        generate_file_response.assert_called_once_with(mock.ANY, 'text/plain', False, name=sub_path_file)


class GenerateFileResponseTests(SimpleTestCase):

    def get_headers_from_response(self, response):
        if isinstance(response, FileResponse):
            headers = {}
            if hasattr(response, '_headers'):
                for _, v in response._headers.items():
                    headers[v[0]] = v[1]
            else:
                headers = response.headers

            return headers
        else:
            raise Exception("Response must be instance of an 'FileResponse'")

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="utf-8")
    @ mock.patch('ESSArch_Core.util.get_filename_from_file_obj', return_value="some_file_name.txt")
    def test_when_utf8_and_file_obj_has_name_then_return_inline_file_response(self, get_charset, get_file_name):
        content_type = 'text/plain'

        resp = generate_file_response(open(__file__, 'rb'), content_type)
        headers = self.get_headers_from_response(resp)

        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Length': str(os.path.getsize(__file__)),
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'inline; filename="{}"'.format("some_file_name.txt")
            }
        )

        self.assertEqual(type(resp), FileResponse)

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="utf-8")
    @ mock.patch('ESSArch_Core.util.get_filename_from_file_obj', return_value=None)
    def test_when_utf8_and_no_filename(self, get_charset, get_filename):
        content_type = 'text/plain'

        resp = generate_file_response(open(__file__, 'rb'), content_type)
        headers = self.get_headers_from_response(resp)
        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Length': str(os.path.getsize(__file__)),
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'inline; filename="{}"'.format(os.path.basename(__file__)),
            }
        )

        self.assertEqual(type(resp), FileResponse)

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="windows-1252")
    @ mock.patch('ESSArch_Core.util.get_filename_from_file_obj', return_value="some_file_name.txt")
    def test_win1252_and_file_obj_has_name_then_return_inline_file_response(self, get_charset, get_filename):
        content_type = 'text/plain'

        resp = generate_file_response(open(__file__, 'rb'), content_type)
        headers = self.get_headers_from_response(resp)

        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Length': str(os.path.getsize(__file__)),
                'Content-Type': 'text/plain; charset=windows-1252',
                'Content-Disposition': 'inline; filename="{}"'.format("some_file_name.txt")
            }
        )

        self.assertEqual(type(resp), FileResponse)

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="windows-1252")
    @ mock.patch('ESSArch_Core.util.get_filename_from_file_obj', return_value=None)
    def test_win1252_and_no_filename(self, mock_get_charset, mock_get_filename):
        content_type = 'text/plain'

        resp = generate_file_response(open(__file__, 'rb'), content_type)
        headers = self.get_headers_from_response(resp)
        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Length': str(os.path.getsize(__file__)),
                'Content-Type': 'text/plain; charset=windows-1252',
                'Content-Disposition': 'inline; filename="{}"'.format(os.path.basename(__file__)),
            }
        )

        self.assertEqual(type(resp), FileResponse)

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="utf-8")
    def test_when_force_download_and_filename_not_none_then_add_attachment(self, get_charset):
        content_type = 'text/plain'

        resp = generate_file_response(open(__file__, 'rb'), content_type, force_download=True)
        headers = self.get_headers_from_response(resp)

        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Length': str(os.path.getsize(__file__)),
                'Content-Disposition': 'attachment; filename="{}"'.format("test_util.py")
            }
        )

        self.assertEqual(type(resp), FileResponse)

    @ mock.patch('ESSArch_Core.util.get_charset', return_value="utf-8")
    def test_when_filename_is_not_ascii(self, get_charset):
        content_type = 'text/plain'

        resp = generate_file_response(
            ContentFile(b'binary content', 'none_ascii_å_name.txt'),
            content_type,
        )
        headers = self.get_headers_from_response(resp)

        self.assertEqual(
            headers,
            {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': "inline; filename*=utf-8''{}".format("none_ascii_%C3%A5_name.txt")
            }
        )

        self.assertEqual(type(resp), FileResponse)


class DeletePathTests(SimpleTestCase):
    def setUp(self) -> None:
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir)

    def test_delete_directory(self):
        path = os.path.join(self.datadir, 'foo')
        os.mkdir(path)

        delete_path(path)
        self.assertFalse(os.path.exists(path))

    def test_delete_file(self):
        path = os.path.join(self.datadir, 'foo.txt')
        open(path, 'a').close()

        delete_path(path)
        self.assertFalse(os.path.exists(path))

    def test_delete_non_existing_path(self):
        path = os.path.join(self.datadir, 'foo.txt')
        delete_path(path)
        self.assertFalse(os.path.exists(path))


class FindDestinationTests(SimpleTestCase):
    def test_find_destination(self):
        structure = [
            {
                'type': 'file',
                'name': 'mets.xml',
                'use': 'mets_file',
            },
            {
                'type': 'folder',
                'name': 'content',
                'use': 'content',
                'children': [
                    {
                        'type': 'file',
                        "name": 'metadata.xml',
                        'use': 'content_type_specification'
                    },
                    {
                        'type': 'file',
                        "name": 'metadata.xsd',
                        'use': 'content_type_specification_schema'
                    },
                ],
            },
            {
                'type': 'folder',
                'name': 'metadata',
                'use': 'metadata',
                'children': [
                    {
                        'type': 'file',
                        'use': 'xsd_files',
                        'name': 'xsd_files'
                    },
                    {
                        'type': 'file',
                        'name': 'premis.xml',
                        'use': 'preservation_description_file',
                    },
                    {
                        'type': 'file',
                        'name': 'ead.xml',
                        'use': 'archival_description_file',
                    },
                    {
                        'type': 'file',
                        'name': 'eac.xml',
                        'use': 'authoritive_information_file',
                    },
                ]
            },
        ]

        tests = (
            ('mets_file', ('', 'mets.xml')),
            ('xsd_files', ('metadata', 'xsd_files')),
            ('preservation_description_file', ('metadata', 'premis.xml')),
            ('foo', (None, None)),
        )

        for value, expected in tests:
            with self.subTest(value=value):
                self.assertEqual(find_destination(value, structure), expected)
