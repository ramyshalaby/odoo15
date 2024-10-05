# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo.tests import HttpCase, tagged

_logger = logging.getLogger(__name__)


@tagged('-at_install', 'post_install')
class TestUi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['hr.employee'].create({
            'name': 'Thibault',
            'work_email': 'thibault@a.be',
            'tz': 'UTC',
            'employee_type': 'freelance',
        })

    def test_01_ui(self):
        self.start_tour("/", 'planning_test_tour', login='admin')
