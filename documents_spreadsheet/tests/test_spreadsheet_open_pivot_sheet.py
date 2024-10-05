# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from .common import SpreadsheetTestCommon

from odoo.tests import tagged, loaded_demo_data
from odoo.tests.common import HttpCase
from odoo.modules.module import get_module_resource
from odoo.tools import file_open

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestSpreadsheetOpenPivot(SpreadsheetTestCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super(TestSpreadsheetOpenPivot, cls).setUpClass()
        cls.spreadsheet_user.partner_id.country_id = cls.env.ref("base.us")
        cls.env['res.users'].browse(2).partner_id.country_id = cls.env.ref("base.be")
        data_path = get_module_resource('documents_spreadsheet', 'tests', 'test_spreadsheet_data.json')
        with file_open(data_path, 'rb') as f:
            cls.spreadsheet = cls.env["documents.document"].create({
                "handler": "spreadsheet",
                "folder_id": cls.folder.id,
                "raw": f.read(),
                "name": "Partner Spreadsheet Test"
            })

    def test_01_spreadsheet_open_pivot_as_admin(self):
        self.start_tour("/web", "spreadsheet_open_pivot_sheet", login="admin")

    def test_01_spreadsheet_open_pivot_as_user(self):
        self.start_tour("/web", "spreadsheet_open_pivot_sheet", login="spreadsheetDude")
