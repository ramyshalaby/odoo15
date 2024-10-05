# -*- coding: utf-8 -*-
{
    'name': 'stop odoo activation message v15)',
    'version': '1.0',
    'category': 'Extra Tools',
    'summary': 'Prevent odoo activation message in home menu',
    'description': """
This module prevent odoo activation message in main home screen for odoo enterprise
    """,

    'depends': ['web_enterprise'],
    'data': [],
    'assets': {
        'web.assets_qweb': [
            'stop_odoo_activation_message/static/src/xml/home_menu.xml'
        ],
    },

    'author': 'prt.c.bhatti@gmail.com',
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
