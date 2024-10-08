# -*- coding: utf-8 -*-
# pylint: disable=C0326
from unittest.mock import patch
from freezegun import freeze_time

from .common import TestAccountReportsCommon
from odoo import fields, Command
from odoo.tests import tagged
from odoo.tests.common import Form


@tagged('post_install', '-at_install')
class TestTaxReport(TestAccountReportsCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create country data

        cls.fiscal_country = cls.env['res.country'].create({
            'name': "Discworld",
            'code': 'DW',
        })

        cls.country_state_1 = cls.env['res.country.state'].create({
            'name': "Ankh Morpork",
            'code': "AM",
            'country_id': cls.fiscal_country.id,
        })

        cls.country_state_2 = cls.env['res.country.state'].create({
            'name': "Counterweight Continent",
            'code': "CC",
            'country_id': cls.fiscal_country.id,
        })

        # Setup fiscal data
        cls.company_data['company'].write({
            'country_id': cls.fiscal_country.id,  # Will also set fiscal_country_id
            'state_id': cls.country_state_1.id,  # Not necessary at the moment; put there for consistency and robustness with possible future changes
            'account_tax_periodicity': 'trimester',
        })

        # So that we can easily instantiate test tax templates within this country
        cls.company_data['company'].chart_template_id.country_id = cls.fiscal_country
        tax_templates = cls.env['account.tax.template'].search([('chart_template_id', '=', cls.company_data['company'].chart_template_id.id)])
        tax_templates.mapped('tax_group_id').write({
            'country_id': cls.fiscal_country.id,
        })

        # Prepare tax groups
        cls.tax_group_1 = cls._instantiate_basic_test_tax_group()
        cls.tax_group_2 = cls._instantiate_basic_test_tax_group()

        # Prepare tax accounts
        cls.tax_account_1 = cls.env['account.account'].create({
            'name': 'Tax Account',
            'code': '250000',
            'user_type_id': cls.env.ref('account.data_account_type_current_liabilities').id,
            'company_id': cls.company_data['company'].id,
        })

        cls.tax_account_2 = cls.env['account.account'].create({
            'name': 'Tax Account',
            'code': '250001',
            'user_type_id': cls.env.ref('account.data_account_type_current_liabilities').id,
            'company_id': cls.company_data['company'].id,
        })

        # ==== Sale taxes: group of two taxes having type_tax_use = 'sale' ====
        cls.sale_tax_percentage_incl_1 = cls.env['account.tax'].create({
            'name': 'sale_tax_percentage_incl_1',
            'amount': 20.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'price_include': True,
            'tax_group_id': cls.tax_group_1.id,
        })

        cls.sale_tax_percentage_excl = cls.env['account.tax'].create({
            'name': 'sale_tax_percentage_excl',
            'amount': 10.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_group_id': cls.tax_group_1.id,
        })

        cls.sale_tax_group = cls.env['account.tax'].create({
            'name': 'sale_tax_group',
            'amount_type': 'group',
            'type_tax_use': 'sale',
            'children_tax_ids': [(6, 0, (cls.sale_tax_percentage_incl_1 + cls.sale_tax_percentage_excl).ids)],
        })

        cls.move_sale = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': '2016-01-01',
            'journal_id': cls.company_data['default_journal_sale'].id,
            'line_ids': [
                (0, 0, {
                    'debit': 1320.0,
                    'credit': 0.0,
                    'account_id': cls.company_data['default_account_receivable'].id,
                }),
                (0, 0, {
                    'debit': 0.0,
                    'credit': 120.0,
                    'account_id': cls.tax_account_1.id,
                    'tax_repartition_line_id': cls.sale_tax_percentage_excl.invoice_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax').id,
                }),
                (0, 0, {
                    'debit': 0.0,
                    'credit': 200.0,
                    'account_id': cls.tax_account_1.id,
                    'tax_repartition_line_id': cls.sale_tax_percentage_incl_1.invoice_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax').id,
                    'tax_ids': [(6, 0, cls.sale_tax_percentage_excl.ids)]
                }),
                (0, 0, {
                    'debit': 0.0,
                    'credit': 1000.0,
                    'account_id': cls.company_data['default_account_revenue'].id,
                    'tax_ids': [(6, 0, cls.sale_tax_group.ids)]
                }),
            ],
        })
        cls.move_sale.action_post()

        # ==== Purchase taxes: group of taxes having type_tax_use = 'none' ====

        cls.none_tax_percentage_incl_2 = cls.env['account.tax'].create({
            'name': 'none_tax_percentage_incl_2',
            'amount': 20.0,
            'amount_type': 'percent',
            'type_tax_use': 'none',
            'price_include': True,
            'tax_group_id': cls.tax_group_2.id,
        })

        cls.none_tax_percentage_excl = cls.env['account.tax'].create({
            'name': 'none_tax_percentage_excl',
            'amount': 30.0,
            'amount_type': 'percent',
            'type_tax_use': 'none',
            'tax_group_id': cls.tax_group_2.id,
        })

        cls.purchase_tax_group = cls.env['account.tax'].create({
            'name': 'purchase_tax_group',
            'amount_type': 'group',
            'type_tax_use': 'purchase',
            'children_tax_ids': [(6, 0, (cls.none_tax_percentage_incl_2 + cls.none_tax_percentage_excl).ids)],
        })

        cls.move_purchase = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': '2016-01-01',
            'journal_id': cls.company_data['default_journal_purchase'].id,
            'line_ids': [
                (0, 0, {
                    'debit': 0.0,
                    'credit': 3120.0,
                    'account_id': cls.company_data['default_account_payable'].id,
                }),
                (0, 0, {
                    'debit': 720.0,
                    'credit': 0.0,
                    'account_id': cls.tax_account_1.id,
                    'tax_repartition_line_id': cls.none_tax_percentage_excl.invoice_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax').id,
                }),
                (0, 0, {
                    'debit': 400.0,
                    'credit': 0.0,
                    'account_id': cls.tax_account_1.id,
                    'tax_repartition_line_id': cls.none_tax_percentage_incl_2.invoice_repartition_line_ids.filtered(lambda x: x.repartition_type == 'tax').id,
                    'tax_ids': [(6, 0, cls.none_tax_percentage_excl.ids)]
                }),
                (0, 0, {
                    'debit': 2000.0,
                    'credit': 0.0,
                    'account_id': cls.company_data['default_account_expense'].id,
                    'tax_ids': [(6, 0, cls.purchase_tax_group.ids)]
                }),
            ],
        })
        cls.move_purchase.action_post()

        #Instantiate test data for fiscal_position option of the tax report (both for checking the report and VAT closing)

        # Create a foreign partner
        cls.test_fpos_foreign_partner = cls.env['res.partner'].create({
            'name': "Mare Cel",
            'country_id': cls.fiscal_country.id,
            'state_id': cls.country_state_2.id,
        })

        # Create a tax report and some taxes for it
        cls.basic_tax_report = cls.env['account.tax.report'].create({
            'name': "The Unseen Tax Report",
            'country_id': cls.fiscal_country.id
        })

        cls.test_fpos_tax_sale = cls._add_basic_tax_for_report(
            cls.basic_tax_report, 50, 'sale', cls.tax_group_1,
            [(30, cls.tax_account_1, False), (70, cls.tax_account_1, True), (-10, cls.tax_account_2, True)]
        )

        cls.test_fpos_tax_purchase = cls._add_basic_tax_for_report(
            cls.basic_tax_report, 50, 'purchase', cls.tax_group_2,
            [(10, cls.tax_account_1, False), (60, cls.tax_account_1, True), (-5, cls.tax_account_2, True)]
        )

        # Create a fiscal_position to automatically map the default tax for partner b to our test tax
        cls.foreign_vat_fpos = cls.env['account.fiscal.position'].create({
            'name': "Test fpos",
            'auto_apply': True,
            'country_id': cls.fiscal_country.id,
            'state_ids': cls.country_state_2.ids,
            'foreign_vat': '12345',
        })

        # Create some domestic invoices (not all in the same closing period)
        cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2020-12-22', post=True, amounts=[28000], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2021-01-22', post=True, amounts=[200], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('out_refund', partner=cls.partner_a, invoice_date='2021-01-12', post=True, amounts=[20], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('in_invoice', partner=cls.partner_a, invoice_date='2021-03-12', post=True, amounts=[400], taxes=cls.test_fpos_tax_purchase)
        cls.init_invoice('in_refund', partner=cls.partner_a, invoice_date='2021-03-20', post=True, amounts=[60], taxes=cls.test_fpos_tax_purchase)
        cls.init_invoice('in_invoice', partner=cls.partner_a, invoice_date='2021-04-07', post=True, amounts=[42000], taxes=cls.test_fpos_tax_purchase)

        # Create some foreign invoices (not all in the same closing period)
        cls.init_invoice('out_invoice', partner=cls.test_fpos_foreign_partner, invoice_date='2020-12-13', post=True, amounts=[26000], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('out_invoice', partner=cls.test_fpos_foreign_partner, invoice_date='2021-01-16', post=True, amounts=[800], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('out_refund', partner=cls.test_fpos_foreign_partner, invoice_date='2021-01-30', post=True, amounts=[200], taxes=cls.test_fpos_tax_sale)
        cls.init_invoice('in_invoice', partner=cls.test_fpos_foreign_partner, invoice_date='2021-02-01', post=True, amounts=[1000], taxes=cls.test_fpos_tax_purchase)
        cls.init_invoice('in_refund', partner=cls.test_fpos_foreign_partner, invoice_date='2021-03-02', post=True, amounts=[600], taxes=cls.test_fpos_tax_purchase)
        cls.init_invoice('in_refund', partner=cls.test_fpos_foreign_partner, invoice_date='2021-05-02', post=True, amounts=[10000], taxes=cls.test_fpos_tax_purchase)

    @classmethod
    def _instantiate_basic_test_tax_group(cls):
        return cls.env['account.tax.group'].create({
            'name': 'Test tax group',
            'property_tax_receivable_account_id': cls.company_data['default_account_receivable'].copy().id,
            'property_tax_payable_account_id': cls.company_data['default_account_payable'].copy().id,
        })

    @classmethod
    def _add_basic_tax_for_report(cls, tax_report, percentage, type_tax_use, tax_group, tax_repartition, company=None):
        """ Creates a basic test tax, as well as tax report lines and tags, connecting them all together.

        A tax report line will be created within tax report for each of the elements in tax_repartition,
        for both invoice and refund, so that the resulting repartition lines each reference their corresponding
        report line. Negative tags will be assign for refund lines; postive tags for invoice ones.

        :param tax_report: The report to create lines for.
        :param percentage: The created tax has amoun_type='percent'. This parameter contains its amount.
        :param type_tax_use: type_tax_use of the tax to create
        :param tax_repartition: List of tuples in the form [(factor_percent, account, use_in_tax_closing)], one tuple
                                for each tax repartition line to create (base lines will be automatically created).
        """
        tax = cls.env['account.tax'].create({
            'name': "%s - %s - %s" % (type_tax_use, percentage, tax_report.name),
            'amount': percentage,
            'amount_type': 'percent',
            'type_tax_use': type_tax_use,
            'tax_group_id': tax_group.id,
            'country_id': tax_report.country_id.id,
            'company_id': company.id if company else cls.env.company.id,
        })

        to_write = {}
        for move_type_suffix in ('invoice', 'refund'):
            tax_negate = move_type_suffix == 'refund'
            report_line_sequence = tax_report.line_ids[-1].sequence + 1 if tax_report.line_ids else 0


            # Create a report line for the base
            base_report_line_name = '%s-%s-base' % (tax.id, move_type_suffix)
            base_report_line = cls._create_tax_report_line(base_report_line_name, tax_report, tag_name=base_report_line_name, sequence=report_line_sequence)
            report_line_sequence += 1

            base_tag = base_report_line.tag_ids.filtered(lambda x: x.tax_negate == tax_negate)

            repartition_vals = [
                Command.clear(),
                Command.create({'repartition_type': 'base', 'factor_percent': 100, 'tag_ids': base_tag.ids}),
            ]

            for (factor_percent, account, use_in_tax_closing) in tax_repartition:
                # Create a report line for the reparition line
                tax_report_line_name = "%s-%s-%s" % (tax.id, move_type_suffix, factor_percent)
                tax_report_line = cls._create_tax_report_line(tax_report_line_name, tax_report, tag_name=tax_report_line_name, sequence=report_line_sequence)
                report_line_sequence += 1

                tax_tag = tax_report_line.tag_ids.filtered(lambda x: x.tax_negate == tax_negate)

                repartition_vals.append(Command.create({
                    'account_id': account.id if account else None,
                    'factor_percent': factor_percent,
                    'use_in_tax_closing': use_in_tax_closing,
                    'tag_ids': tax_tag.ids,
                }))

            to_write['%s_repartition_line_ids' % move_type_suffix] = repartition_vals

        tax.write(to_write)

        return tax

    def _assert_vat_closing(self, options, closing_vals_by_fpos):
        """ Checks the result of the VAT closing

        :param options: the tax report options to make the closing for
        :param closing_vals_by_fpos: A list of dict(fiscal_position: [dict(line_vals)], where fiscal_position is (possibly empty)
                                     account.fiscal.position record, and line_vals, the expected values for each closing move lines.
                                     In case options contains the 'multi_company' key, a tuple (company, fiscal_position) replaces the
                                     fiscal_position key
        """
        report = self.env['account.generic.tax.report']
        with patch.object(type(report), '_get_vat_report_attachments', autospec=True, side_effect=lambda *args, **kwargs: []):
            vat_closing_moves = report._generate_tax_closing_entries(options)

            if options.get('multi_company'):
                closing_moves_by_fpos = {(move.company_id, move.fiscal_position_id): move for move in vat_closing_moves}
            else:
                closing_moves_by_fpos = {move.fiscal_position_id: move for move in vat_closing_moves}

            for key, closing_vals in closing_vals_by_fpos.items():
                vat_closing_move = closing_moves_by_fpos[key]
                self.assertRecordValues(vat_closing_move.line_ids, closing_vals)
            self.assertEqual(len(closing_vals_by_fpos), len(vat_closing_moves), "Exactly one move should have been generated per fiscal position; nothing else.")

    def test_vat_closing_single_fpos(self):
        """ Tests the VAT closing when a foreign VAT fiscal position is selected on the tax report
        """
        options = self._init_options(
            self.env['account.generic.tax.report'], fields.Date.from_string('2021-01-15'), fields.Date.from_string('2021-02-01'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': self.foreign_vat_fpos.id}
        )

        self._assert_vat_closing(options, {
            self.foreign_vat_fpos: [
                # sales: 800 * 0.5 * 0.7 - 200 * 0.5 * 0.7
                {'debit': 210,      'credit': 0.0,      'account_id': self.tax_account_1.id},
                # sales: 800 * 0.5 * (-0.1) - 200 * 0.5 * (-0.1)
                {'debit': 0,        'credit': 30,       'account_id': self.tax_account_2.id},
                # purchases: 1000 * 0.5 * 0.6 - 600 * 0.5 * 0.6
                {'debit': 0,        'credit': 120,      'account_id': self.tax_account_1.id},
                # purchases: 1000 * 0.5 * (-0.05) - 600 * 0.5 * (-0.05)
                {'debit': 10,       'credit': 0,        'account_id': self.tax_account_2.id},
                # For sales operations
                {'debit': 0,        'credit': 180,      'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                # For purchase operations
                {'debit': 110,      'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
            ]
        })

    def test_vat_closing_domestic(self):
        """ Tests the VAT closing when a foreign VAT fiscal position is selected on the tax report
        """
        options = self._init_options(
            self.env['account.generic.tax.report'], fields.Date.from_string('2021-01-15'), fields.Date.from_string('2021-02-01'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': 'domestic'}
        )

        self._assert_vat_closing(options, {
            self.env['account.fiscal.position']: [
                # sales: 200 * 0.5 * 0.7 - 20 * 0.5 * 0.7
                {'debit': 63,       'credit': 0.0,      'account_id': self.tax_account_1.id},
                # sales: 200 * 0.5 * (-0.1) - 20 * 0.5 * (-0.1)
                {'debit': 0,        'credit': 9,        'account_id': self.tax_account_2.id},
                # purchases: 400 * 0.5 * 0.6 - 60 * 0.5 * 0.6
                {'debit': 0,        'credit': 102,      'account_id': self.tax_account_1.id},
                # purchases: 400 * 0.5 * (-0.05) - 60 * 0.5 * (-0.05)
                {'debit': 8.5,      'credit': 0,        'account_id': self.tax_account_2.id},
                # For sales operations
                {'debit': 0,        'credit': 54,       'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                # For purchase operations
                {'debit': 93.5,     'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
            ]
        })

    def test_vat_closing_everything(self):
        """ Tests the VAT closing when the option to show all foreign VAT fiscal positions is activated.
        One closing move should then be generated per fiscal position.
        """
        options = self._init_options(
            self.env['account.generic.tax.report'], fields.Date.from_string('2021-01-15'), fields.Date.from_string('2021-02-01'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': 'all'}
        )

        self._assert_vat_closing(options, {
            # From test_vat_closing_domestic
            self.env['account.fiscal.position']: [
                # sales: 200 * 0.5 * 0.7 - 20 * 0.5 * 0.7
                {'debit': 63,       'credit': 0.0,      'account_id': self.tax_account_1.id},
                # sales: 200 * 0.5 * (-0.1) - 20 * 0.5 * (-0.1)
                {'debit': 0,        'credit': 9,        'account_id': self.tax_account_2.id},
                # purchases: 400 * 0.5 * 0.6 - 60 * 0.5 * 0.6
                {'debit': 0,        'credit': 102,      'account_id': self.tax_account_1.id},
                # purchases: 400 * 0.5 * (-0.05) - 60 * 0.5 * (-0.05)
                {'debit': 8.5,      'credit': 0,        'account_id': self.tax_account_2.id},
                # For sales operations
                {'debit': 0,        'credit': 54,       'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                # For purchase operations
                {'debit': 93.5,     'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
            ],

            # From test_vat_closing_single_fpos
            self.foreign_vat_fpos: [
                # sales: 800 * 0.5 * 0.7 - 200 * 0.5 * 0.7
                {'debit': 210,      'credit': 0.0,      'account_id': self.tax_account_1.id},
                # sales: 800 * 0.5 * (-0.1) - 200 * 0.5 * (-0.1)
                {'debit': 0,        'credit': 30,       'account_id': self.tax_account_2.id},
                # purchases: 1000 * 0.5 * 0.6 - 600 * 0.5 * 0.6
                {'debit': 0,        'credit': 120,      'account_id': self.tax_account_1.id},
                # purchases: 1000 * 0.5 * (-0.05) - 600 * 0.5 * (-0.05)
                {'debit': 10,       'credit': 0,        'account_id': self.tax_account_2.id},
                # For sales operations
                {'debit': 0,        'credit': 180,      'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                # For purchase operations
                {'debit': 110,      'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
            ],
        })

    def test_vat_closing_generic(self):
        """ VAT closing for the generic report should create one closing move per fiscal position + a domestic one.
        One closing move should then be generated per fiscal position.
        """
        for generic_report in ('generic', 'generic_grouped_tax_account', 'generic_grouped_account_tax'):
            options = self._init_options(
                self.env['account.generic.tax.report'], fields.Date.from_string('2021-01-15'), fields.Date.from_string('2021-02-01'),
                {'tax_report': generic_report}
            )

            self._assert_vat_closing(options, {
                # From test_vat_closing_domestic
                self.env['account.fiscal.position']: [
                    # sales: 200 * 0.5 * 0.7 - 20 * 0.5 * 0.7
                    {'debit': 63,       'credit': 0.0,      'account_id': self.tax_account_1.id},
                    # sales: 200 * 0.5 * (-0.1) - 20 * 0.5 * (-0.1)
                    {'debit': 0,        'credit': 9,        'account_id': self.tax_account_2.id},
                    # purchases: 400 * 0.5 * 0.6 - 60 * 0.5 * 0.6
                    {'debit': 0,        'credit': 102,      'account_id': self.tax_account_1.id},
                    # purchases: 400 * 0.5 * (-0.05) - 60 * 0.5 * (-0.05)
                    {'debit': 8.5,      'credit': 0,        'account_id': self.tax_account_2.id},
                    # For sales operations
                    {'debit': 0,        'credit': 54,       'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                    # For purchase operations
                    {'debit': 93.5,     'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
                ],

                # From test_vat_closing_single_fpos
                self.foreign_vat_fpos: [
                    # sales: 800 * 0.5 * 0.7 - 200 * 0.5 * 0.7
                    {'debit': 210,      'credit': 0.0,      'account_id': self.tax_account_1.id},
                    # sales: 800 * 0.5 * (-0.1) - 200 * 0.5 * (-0.1)
                    {'debit': 0,        'credit': 30,       'account_id': self.tax_account_2.id},
                    # purchases: 1000 * 0.5 * 0.6 - 600 * 0.5 * 0.6
                    {'debit': 0,        'credit': 120,      'account_id': self.tax_account_1.id},
                    # purchases: 1000 * 0.5 * (-0.05) - 600 * 0.5 * (-0.05)
                    {'debit': 10,       'credit': 0,        'account_id': self.tax_account_2.id},
                    # For sales operations
                    {'debit': 0,        'credit': 180,      'account_id': self.tax_group_1.property_tax_payable_account_id.id},
                    # For purchase operations
                    {'debit': 110,      'credit': 0,        'account_id': self.tax_group_2.property_tax_receivable_account_id.id},
                ],
            })

    def test_tax_report_fpos_domestic(self):
        """ Test tax report's content for 'domestic' foreign VAT fiscal position option.
        """
        report = self.env['account.generic.tax.report']
        options = self._init_options(
            report, fields.Date.from_string('2021-01-01'), fields.Date.from_string('2021-03-31'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': 'domestic'}
        )
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                                                          Balance
            [   0,                                                            1],
            [
                # out_invoice
                ('%s-invoice-base' % self.test_fpos_tax_sale.id,           200),
                ('%s-invoice-30' % self.test_fpos_tax_sale.id,              30),
                ('%s-invoice-70' % self.test_fpos_tax_sale.id,              70),
                ('%s-invoice--10' % self.test_fpos_tax_sale.id,            -10),

                #out_refund
                ('%s-refund-base' % self.test_fpos_tax_sale.id,            -20),
                ('%s-refund-30' % self.test_fpos_tax_sale.id,               -3),
                ('%s-refund-70' % self.test_fpos_tax_sale.id,               -7),
                ('%s-refund--10' % self.test_fpos_tax_sale.id,               1),

                #in_invoice
                ('%s-invoice-base' % self.test_fpos_tax_purchase.id,       400),
                ('%s-invoice-10' % self.test_fpos_tax_purchase.id,          20),
                ('%s-invoice-60' % self.test_fpos_tax_purchase.id,         120),
                ('%s-invoice--5' % self.test_fpos_tax_purchase.id,         -10),

                #in_refund
                ('%s-refund-base' % self.test_fpos_tax_purchase.id,        -60),
                ('%s-refund-10' % self.test_fpos_tax_purchase.id,           -3),
                ('%s-refund-60' % self.test_fpos_tax_purchase.id,          -18),
                ('%s-refund--5' % self.test_fpos_tax_purchase.id,          1.5),
            ],
        )

    def test_tax_report_fpos_foreign(self):
        """ Test tax report's content with a foreign VAT fiscal position.
        """
        report = self.env['account.generic.tax.report']
        options = self._init_options(
            report, fields.Date.from_string('2021-01-01'), fields.Date.from_string('2021-03-31'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': self.foreign_vat_fpos.id}
        )
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                                                          Balance
            [   0,                                                            1],
            [
                # out_invoice
                ('%s-invoice-base' % self.test_fpos_tax_sale.id,           800),
                ('%s-invoice-30' % self.test_fpos_tax_sale.id,             120),
                ('%s-invoice-70' % self.test_fpos_tax_sale.id,             280),
                ('%s-invoice--10' % self.test_fpos_tax_sale.id,            -40),

                #out_refund
                ('%s-refund-base' % self.test_fpos_tax_sale.id,           -200),
                ('%s-refund-30' % self.test_fpos_tax_sale.id,              -30),
                ('%s-refund-70' % self.test_fpos_tax_sale.id,              -70),
                ('%s-refund--10' % self.test_fpos_tax_sale.id,              10),

                #in_invoice
                ('%s-invoice-base' % self.test_fpos_tax_purchase.id,      1000),
                ('%s-invoice-10' % self.test_fpos_tax_purchase.id,          50),
                ('%s-invoice-60' % self.test_fpos_tax_purchase.id,         300),
                ('%s-invoice--5' % self.test_fpos_tax_purchase.id,         -25),

                #in_refund
                ('%s-refund-base' % self.test_fpos_tax_purchase.id,       -600),
                ('%s-refund-10' % self.test_fpos_tax_purchase.id,          -30),
                ('%s-refund-60' % self.test_fpos_tax_purchase.id,         -180),
                ('%s-refund--5' % self.test_fpos_tax_purchase.id,           15),
            ],
        )

    def test_tax_report_fpos_everything(self):
        """ Test tax report's content for 'all' foreign VAT fiscal position option.
        """
        report = self.env['account.generic.tax.report']
        options = self._init_options(
            report, fields.Date.from_string('2021-01-01'), fields.Date.from_string('2021-03-31'),
            {'tax_report': self.basic_tax_report.id, 'fiscal_position': 'all'}
        )
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                                                          Balance
            [   0,                                                            1],
            [
                # out_invoice
                ('%s-invoice-base' % self.test_fpos_tax_sale.id,          1000),
                ('%s-invoice-30' % self.test_fpos_tax_sale.id,             150),
                ('%s-invoice-70' % self.test_fpos_tax_sale.id,             350),
                ('%s-invoice--10' % self.test_fpos_tax_sale.id,            -50),

                #out_refund
                ('%s-refund-base' % self.test_fpos_tax_sale.id,           -220),
                ('%s-refund-30' % self.test_fpos_tax_sale.id,              -33),
                ('%s-refund-70' % self.test_fpos_tax_sale.id,              -77),
                ('%s-refund--10' % self.test_fpos_tax_sale.id,              11),

                #in_invoice
                ('%s-invoice-base' % self.test_fpos_tax_purchase.id,      1400),
                ('%s-invoice-10' % self.test_fpos_tax_purchase.id,          70),
                ('%s-invoice-60' % self.test_fpos_tax_purchase.id,         420),
                ('%s-invoice--5' % self.test_fpos_tax_purchase.id,         -35),

                #in_refund
                ('%s-refund-base' % self.test_fpos_tax_purchase.id,       -660),
                ('%s-refund-10' % self.test_fpos_tax_purchase.id,          -33),
                ('%s-refund-60' % self.test_fpos_tax_purchase.id,         -198),
                ('%s-refund--5' % self.test_fpos_tax_purchase.id,         16.5),
            ],
        )

    def test_tax_report_single_fpos(self):
        """ When opening the tax report from a foreign country for which there exists only one
        foreing VAT fiscal position, this fiscal position should be selected by default in the
        report's options.
        """
        new_country = self.env['res.country'].create({
            'name': "The Principality of Zeon",
            'code': 'PZ',
        })
        new_tax_report = self.env['account.tax.report'].create({
            'name': "",
            'country_id': new_country.id
        })
        foreign_vat_fpos = self.env['account.fiscal.position'].create({
            'name': "Test fpos",
            'country_id': new_country.id,
            'foreign_vat': '422211',
        })
        options = self._init_options(
            self.env['account.generic.tax.report'], fields.Date.from_string('2021-01-01'), fields.Date.from_string('2021-03-31'),
            {'tax_report': new_tax_report.id}
        )
        self.assertEqual(options['fiscal_position'], foreign_vat_fpos.id, "When only one VAT fiscal position is available for a non-domestic country, it should be chosen by default")

    def test_tax_report_grid(self):
        company = self.company_data['company']

        # We generate a tax report with the following layout
        #/Base
        #   - Base 42%
        #   - Base 11%
        #/Tax
        #   - Tax 42%
        #       - 10.5%
        #       - 31.5%
        #   - Tax 11%
        #/Tax difference (42% - 11%)

        tax_report = self.env['account.tax.report'].create({
            'name': 'Test',
            'country_id': company.account_fiscal_country_id.id,
        })

        # We create the lines in a different order from the one they have in report,
        # so that we ensure sequence is taken into account properly when rendering the report
        tax_section = self._create_tax_report_line('Tax', tax_report, sequence=2)
        base_section = self._create_tax_report_line('Base', tax_report, sequence=1)
        base_11_line = self._create_tax_report_line('Base 11%', tax_report, sequence=2, parent_line=base_section, tag_name='base_11')
        base_42_line = self._create_tax_report_line('Base 42%', tax_report, sequence=1, parent_line=base_section, tag_name='base_42')
        tax_42_section = self._create_tax_report_line('Tax 42%', tax_report, sequence=1, parent_line=tax_section, code='tax_42')
        tax_31_5_line = self._create_tax_report_line('Tax 31.5%', tax_report, sequence=2, parent_line=tax_42_section, tag_name='tax_31_5')
        tax_10_5_line = self._create_tax_report_line('Tax 10.5%', tax_report, sequence=1, parent_line=tax_42_section, tag_name='tax_10_5')
        tax_11_line = self._create_tax_report_line('Tax 10.5%', tax_report, sequence=2, parent_line=tax_section, tag_name='tax_11', code='tax_11')
        tax_neg_10_line = self._create_tax_report_line('Tax -10%', tax_report, sequence=3, parent_line=tax_section, tag_name='tax_neg_10', code='tax_neg_10')
        tax_difference_line = self._create_tax_report_line('Tax difference (42%-11%)', tax_report, sequence=3, formula='tax_42 - tax_11')

        # Create two taxes linked to report lines
        tax_template_11 = self.env['account.tax.template'].create({
            'name': 'Impôt sur les revenus',
            'amount': '11',
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'chart_template_id': company.chart_template_id.id,
            'invoice_repartition_line_ids': [
                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'plus_report_line_ids': [base_11_line.id],
                }),

                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'plus_report_line_ids': [tax_11_line.id],
                }),
            ],
            'refund_repartition_line_ids': [
                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'minus_report_line_ids': [base_11_line.id],
                }),

                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'minus_report_line_ids': [tax_11_line.id],
                }),
            ],
        })

        tax_template_42 = self.env['account.tax.template'].create({
            'name': 'Impôt sur les revenants',
            'amount': '42',
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'chart_template_id': company.chart_template_id.id,
            'invoice_repartition_line_ids': [
                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'plus_report_line_ids': [base_42_line.id],
                }),

                (0,0, {
                    'factor_percent': 25,
                    'repartition_type': 'tax',
                    'plus_report_line_ids': [tax_10_5_line.id],
                }),

                (0,0, {
                    'factor_percent': 75,
                    'repartition_type': 'tax',
                    'plus_report_line_ids': [tax_31_5_line.id],
                }),

                (0,0, {
                    'factor_percent': -10,
                    'repartition_type': 'tax',
                    'minus_report_line_ids': [tax_neg_10_line.id],
                }),
            ],
            'refund_repartition_line_ids': [
                (0,0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'minus_report_line_ids': [base_42_line.id],
                }),

                (0,0, {
                    'factor_percent': 25,
                    'repartition_type': 'tax',
                    'minus_report_line_ids': [tax_10_5_line.id],
                }),

                (0,0, {
                    'factor_percent': 75,
                    'repartition_type': 'tax',
                    'minus_report_line_ids': [tax_31_5_line.id],
                }),

                (0,0, {
                    'factor_percent': -10,
                    'repartition_type': 'tax',
                    'plus_report_line_ids': [tax_neg_10_line.id],
                }),
            ],
        })
        # The templates needs an xmlid in order so that we can call _generate_tax
        self.env['ir.model.data'].create({
            'name': 'account_reports.test_tax_report_tax_11',
            'module': 'account_reports',
            'res_id': tax_template_11.id,
            'model': 'account.tax.template',
        })
        tax_11 = tax_template_11._generate_tax(company)['tax_template_to_tax'][tax_template_11]

        self.env['ir.model.data'].create({
            'name': 'account_reports.test_tax_report_tax_42',
            'module': 'account_reports',
            'res_id': tax_template_42.id,
            'model': 'account.tax.template',
        })
        tax_42 = tax_template_42._generate_tax(company)['tax_template_to_tax'][tax_template_42]

        # Create an invoice using the tax we just made
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Turlututu',
                'price_unit': 100.0,
                'quantity': 1,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [(6, 0, (tax_11 + tax_42).ids)],
            })],
        })
        invoice.action_post()

        # Generate the report and check the results
        report = self.env['account.generic.tax.report']
        options = self._init_options(report, invoice.date, invoice.date)
        options['tax_report'] = tax_report.id
        report = report.with_context(report._set_context(options))

        # Invalidate the cache to ensure the lines will be fetched in the right order.
        report.invalidate_cache()

        self.assertLinesValues(
            report._get_lines(options),
            #   Name                                Balance
            [   0,                                  1],
            [
                (base_section.name,                 200),
                (base_42_line.name,                 100),
                (base_11_line.name,                 100),
                (tax_section.name,                  57.2),
                (tax_42_section.name,               42),
                (tax_10_5_line.name,                10.5),
                (tax_31_5_line.name,                31.5),
                (tax_11_line.name,                  11),
                (tax_neg_10_line.name,              4.2),
                (tax_difference_line.name,          31),
            ],
        )

        # We refund the invoice
        refund_wizard = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=invoice.ids).create({
            'reason': 'Test refund tax repartition',
            'refund_method': 'cancel',
            'journal_id': invoice.journal_id.id,
            'date_mode': 'entry',
        })
        refund_wizard.reverse_moves()

        # We check the taxes on refund have impacted the report properly (everything should be 0)
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                                Balance
            [   0,                                  1],
            [
                (base_section.name,                 0),
                (base_42_line.name,                 0),
                (base_11_line.name,                 0),
                (tax_section.name,                  0),
                (tax_42_section.name,               0),
                (tax_10_5_line.name,                0),
                (tax_31_5_line.name,                0),
                (tax_11_line.name,                  0),
                (tax_neg_10_line.name,              0),
                (tax_difference_line.name,          0),
            ],
        )

    def _create_caba_taxes_for_report_lines(self, report_lines_dict, company):
        """ Creates cash basis taxes with a specific test repartition and maps them to
        the provided tax_report lines.

        :param report_lines_dict:  A dictionnary mapping tax_type_use values to
                                   tax report lines records
        :param company:            The company to create the test tags for

        :return:                   The created account.tax objects
        """
        rslt = self.env['account.tax']
        for tax_type, report_line in report_lines_dict.items():
            tax_template = self.env['account.tax.template'].create({
                'name': 'Impôt sur tout ce qui bouge',
                'amount': '20',
                'amount_type': 'percent',
                'type_tax_use': tax_type,
                'chart_template_id': company.chart_template_id.id,
                'tax_exigibility': 'on_payment',
                'invoice_repartition_line_ids': [
                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'base',
                        'plus_report_line_ids': report_line.ids,
                    }),

                    (0,0, {
                        'factor_percent': 25,
                        'repartition_type': 'tax',
                        'plus_report_line_ids': report_line.ids,
                    }),

                    (0,0, {
                        'factor_percent': 75,
                        'repartition_type': 'tax',
                        'plus_report_line_ids': report_line.ids,
                    }),
                ],
                'refund_repartition_line_ids': [
                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'base',
                        'minus_report_line_ids': report_line.ids,
                    }),

                    (0,0, {
                        'factor_percent': 25,
                        'repartition_type': 'tax',
                        'minus_report_line_ids': report_line.ids,
                    }),

                    (0,0, {
                        'factor_percent': 75,
                        'repartition_type': 'tax',
                    }),
                ],
            })

            # The template needs an xmlid in order so that we can call _generate_tax
            self.env['ir.model.data'].create({
                'name': 'account_reports.test_tax_report_tax_' + tax_type,
                'module': 'account_reports',
                'res_id': tax_template.id,
                'model': 'account.tax.template',
            })
            rslt += tax_template._generate_tax(self.env.user.company_id)['tax_template_to_tax'][tax_template]

        return rslt

    def _create_taxes_for_report_lines(self, report_lines_dict, company):
        """ report_lines_dict is a dictionnary mapping tax_type_use values to
        tax report lines.
        """
        rslt = self.env['account.tax']
        for tax_type, report_line in report_lines_dict.items():
            tax_template = self.env['account.tax.template'].create({
                'name': 'Impôt sur tout ce qui bouge',
                'amount': '20',
                'amount_type': 'percent',
                'type_tax_use': tax_type,
                'chart_template_id': company.chart_template_id.id,
                'invoice_repartition_line_ids': [
                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'base',
                        'plus_report_line_ids': report_line[0].ids,
                    }),

                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'tax',
                        'plus_report_line_ids': report_line[1].ids,
                    }),
                ],
                'refund_repartition_line_ids': [
                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'base',
                        'plus_report_line_ids': report_line[0].ids,
                    }),

                    (0,0, {
                        'factor_percent': 100,
                        'repartition_type': 'tax',
                        'plus_report_line_ids': report_line[1].ids,
                    }),
                ],
            })

            # The template needs an xmlid in order so that we can call _generate_tax
            self.env['ir.model.data'].create({
                'name': 'account_reports.test_tax_report_tax_' + tax_type,
                'module': 'account_reports',
                'res_id': tax_template.id,
                'model': 'account.tax.template',
            })
            rslt += tax_template._generate_tax(self.env.user.company_id)['tax_template_to_tax'][tax_template]

        return rslt

    def _run_caba_generic_test(self, expected_columns, expected_lines, on_invoice_created=None, on_all_invoices_created=None, invoice_generator=None):
        """ Generic test function called by several cash basis tests.

        This function creates a new sale and purchase tax, each associated with
        a new tax report line using _create_caba_taxes_for_report_lines.
        It then creates an invoice AND a refund for each of these tax, and finally
        compare the tax report to the expected values, passed in parameters.

        Since _create_caba_taxes_for_report_lines creates asymmetric taxes (their 75%
        repartition line does not impact the report line at refund), we can be sure this
        function helper gives a complete coverage, and does not shadow any result due, for
        example, to some undesired swapping between debit and credit.

        :param expected_columns:          The columns we want the final tax report to contain

        :param expected_lines:            The lines we want the final tax report to contain

        :param on_invoice_created:        A function to be called when a single invoice has
                                          just been created, taking the invoice as a parameter
                                          (This can be used to reconcile the invoice with something, for example)

        :param on_all_invoices_created:   A function to be called when all the invoices corresponding
                                          to a tax type have been created, taking the
                                          recordset of all these invoices as a parameter
                                          (Use it to reconcile invoice and credit note together, for example)

        :param invoice_generator:         A function used to generate an invoice. A default
                                          one is called if none is provided, creating
                                          an invoice with a single line amounting to 100,
                                          with the provided tax set on it.
        """
        def default_invoice_generator(inv_type, partner, account, date, tax):
            return self.env['account.move'].create({
                'move_type': inv_type,
                'partner_id': partner.id,
                'invoice_date': date,
                'invoice_line_ids': [(0, 0, {
                    'name': 'test',
                    'quantity': 1,
                    'account_id': account.id,
                    'price_unit': 100,
                    'tax_ids': [(6, 0, tax.ids)],
                })],
            })

        today = fields.Date.today()

        company = self.company_data['company']
        partner = self.env['res.partner'].create({'name': 'Char Aznable'})

        # Create a tax report
        tax_report = self.env['account.tax.report'].create({
            'name': 'Test',
            'country_id': self.fiscal_country.id,
        })

        # We create some report lines
        report_lines_dict = {
            'sale': self._create_tax_report_line('Sale', tax_report, sequence=1, tag_name='sale'),
            'purchase': self._create_tax_report_line('Purchase', tax_report, sequence=2, tag_name='purchase'),
        }

        # We create a sale and a purchase tax, linked to our report lines' tags
        taxes = self._create_caba_taxes_for_report_lines(report_lines_dict, company)


        # Create invoice and refund using the tax we just made
        invoice_types = {
            'sale': ('out_invoice', 'out_refund'),
            'purchase': ('in_invoice', 'in_refund')
        }

        account_types = {
            'sale': self.env.ref('account.data_account_type_revenue').id,
            'purchase': self.env.ref('account.data_account_type_expenses').id,
        }
        for tax in taxes:
            invoices = self.env['account.move']
            account = self.env['account.account'].search([('company_id', '=', company.id), ('user_type_id', '=', account_types[tax.type_tax_use])], limit=1)
            for inv_type in invoice_types[tax.type_tax_use]:
                invoice = (invoice_generator or default_invoice_generator)(inv_type, partner, account, today, tax)
                invoice.action_post()
                invoices += invoice

                if on_invoice_created:
                    on_invoice_created(invoice)

            if on_all_invoices_created:
                on_all_invoices_created(invoices)

        # Generate the report and check the results
        report = self.env['account.generic.tax.report']
        report_opt = report._get_options({'date': {'period_type': 'custom', 'filter': 'custom', 'date_to': today, 'mode': 'range', 'date_from': today}})
        new_context = report._set_context(report_opt)

        # We check the taxes on invoice have impacted the report properly
        inv_report_lines = report.with_context(new_context)._get_lines(report_opt)

        self.assertLinesValues(inv_report_lines, expected_columns, expected_lines)

    @freeze_time('2023-10-05 02:00:00')
    def test_tax_report_grid_cash_basis(self):
        """ Cash basis moves create for taxes based on payments are handled differently
        by the report; we want to ensure their sign is managed properly.
        """
        # 100 (base, invoice) - 100 (base, refund) + 20 (tax, invoice) - 5 (25% tax, refund) = 15
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     15),
                ('Purchase',                 15),
            ],
            on_invoice_created=self._register_full_payment_for_invoice
        )

    def _register_full_payment_for_invoice(self, invoice):
        """ Fully pay the invoice, so that the cash basis entries are created
        """
        self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
            'payment_date': invoice.date,
        })._create_payments()

    @freeze_time('2023-10-05 02:00:00')
    def test_tax_report_grid_cash_basis_refund(self):
        """ Cash basis moves create for taxes based on payments are handled differently
        by the report; we want to ensure their sign is managed properly. This
        test runs the case where an invoice is reconciled with a refund (created
        separetely, so not cancelling it).
        """
        def reconcile_opposite_types(invoices):
            """ Reconciles the created invoices with their matching refund.
            """
            invoices.mapped('line_ids').filtered(lambda x: x.account_internal_type in ('receivable', 'payable')).reconcile()

        # 100 (base, invoice) - 100 (base, refund) + 20 (tax, invoice) - 5 (25% tax, refund) = 15
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     15),
                ('Purchase',                 15),
            ],
            on_all_invoices_created=reconcile_opposite_types
        )

    @freeze_time('2023-10-05 02:00:00')
    def test_tax_report_grid_cash_basis_misc_pmt(self):
        """ Cash basis moves create for taxes based on payments are handled differently
        by the report; we want to ensure their sign is managed properly. This
        test runs the case where the invoice is paid with a misc operation instead
        of a payment.
        """
        def reconcile_with_misc_pmt(invoice):
            """ Create a misc operation equivalent to a full payment and reconciles
            the invoice with it.
            """
            # Pay the invoice with a misc operation simulating a payment, so that the cash basis entries are created
            invoice_reconcilable_line = invoice.line_ids.filtered(lambda x: x.account_internal_type in ('payable', 'receivable'))
            account = (invoice.line_ids - invoice_reconcilable_line).account_id
            pmt_move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': invoice.date,
                'line_ids': [(0, 0, {
                                'account_id': invoice_reconcilable_line.account_id.id,
                                'debit': invoice_reconcilable_line.credit,
                                'credit': invoice_reconcilable_line.debit,
                            }),
                            (0, 0, {
                                'account_id': account.id,
                                'credit': invoice_reconcilable_line.credit,
                                'debit': invoice_reconcilable_line.debit,
                            })],
            })
            pmt_move.action_post()
            payment_reconcilable_line = pmt_move.line_ids.filtered(lambda x: x.account_internal_type in ('payable', 'receivable'))
            (invoice_reconcilable_line + payment_reconcilable_line).reconcile()

        # 100 (base, invoice) - 100 (base, refund) + 20 (tax, invoice) - 5 (25% tax, refund) = 15
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     15),
                ('Purchase',                 15),
            ],
            on_invoice_created=reconcile_with_misc_pmt
        )

    @freeze_time('2023-10-05 02:00:00')
    def test_caba_no_payment(self):
        """ The cash basis taxes of an unpaid invoice should
        never impact the report.
        """
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     0),
                ('Purchase',                 0),
            ]
        )

    @freeze_time('2023-10-05 02:00:00')
    def test_caba_half_payment(self):
        """ Paying half the amount of the invoice should report half the
        base and tax amounts.
        """
        def register_half_payment_for_invoice(invoice):
            """ Fully pay the invoice, so that the cash basis entries are created
            """
            payment_method_id = self.inbound_payment_method_line if invoice.is_inbound() else self.outbound_payment_method_line
            self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
                'amount': invoice.amount_residual / 2,
                'payment_date': invoice.date,
                'payment_method_line_id': payment_method_id.id,
            })._create_payments()

        # 50 (base, invoice) - 50 (base, refund) + 10 (tax, invoice) - 2.5 (25% tax, refund) = 7.5
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     7.5),
                ('Purchase',                 7.5),
            ],
            on_invoice_created=register_half_payment_for_invoice
        )

    def test_caba_mixed_generic_report(self):
        """ Tests mixing taxes with different tax exigibilities displays correct amounts
        in the generic tax report.
        """
        self.env.company.tax_exigibility = True
        # Create taxes
        regular_tax = self.env['account.tax'].create({
            'name': 'Regular',
            'amount': 42,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            # We use default repartition: 1 base line, 1 100% tax line
        })

        caba_tax = self.env['account.tax'].create({
            'name': 'Cash Basis',
            'amount': 10,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_exigibility': 'on_payment',
            # We use default repartition: 1 base line, 1 100% tax line
        })

        # Create an invoice using them, and post it
        invoice = self.init_invoice(
            'out_invoice',
            invoice_date='2021-07-01',
            post=True,
            amounts=[100],
            taxes=regular_tax + caba_tax,
            company=self.company_data['company'],
        )

        # Check the report only contains non-caba things
        report = self.env['account.generic.tax.report']
        options = self._init_options(report, invoice.date, invoice.date, {'tax_report': 'generic'})
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                         Net              Tax
            [   0,                             1,               2],
            [
                ("Sales",                     '',              42),
                ("Regular (42.0%)",          100,              42),
            ],
        )

        # Pay half of the invoice
        self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
            'amount': 76,
            'payment_date': invoice.date,
            'payment_method_line_id': self.outbound_payment_method_line.id,
        })._create_payments()

        # Check the report again: half the cash basis should be there
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                         Net              Tax
            [   0,                             1,               2],
            [
                ("Sales",                     '',              47),
                ("Regular (42.0%)",          100,              42),
                ("Cash Basis (10.0%)",        50,               5),
            ],
        )

        # Pay the rest
        self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
            'amount': 76,
            'payment_date': invoice.date,
            'payment_method_line_id': self.outbound_payment_method_line.id,
        })._create_payments()

        # Check everything is in the report
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                         Net              Tax
            [   0,                             1,               2],
            [
                ("Sales",                     '',              52),
                ("Regular (42.0%)",          100,              42),
                ("Cash Basis (10.0%)",       100,              10),
            ],
        )

    def test_tax_report_mixed_exigibility_affect_base_generic_invoice(self):
        """ Tests mixing caba and non-caba taxes with one of them affecting the base
        of the other worcs properly on invoices for generic report.
        """
        self.env.company.tax_exigibility = True
        # Create taxes
        regular_tax = self.env['account.tax'].create({
            'name': 'Regular',
            'amount': 42,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'include_base_amount': True,
            'sequence': 0,
            # We use default repartition: 1 base line, 1 100% tax line
        })

        caba_tax = self.env['account.tax'].create({
            'name': 'Cash Basis',
            'amount': 10,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_exigibility': 'on_payment',
            'include_base_amount': True,
            'sequence': 1,
            # We use default repartition: 1 base line, 1 100% tax line
        })

        # Case 1: on_invoice tax affecting on_payment tax's base
        self._run_check_suite_mixed_exigibility_affect_base(
            regular_tax + caba_tax,
            '2021-07-01',
            'generic',
            # Name, Net, Tax
            [   0,                             1,               2],
            # Before payment
            [
                ("Sales",                     '',              42),
                ("Regular (42.0%)",          100,              42),
            ],
            # After paying 30%
            [
                ("Sales",                     '',            46.26),
                ("Regular (42.0%)",          100,              42),
                ("Cash Basis (10.0%)",        42.6,             4.26),
            ],
            # After full payment
            [
                ("Sales",                     '',              56.2),
                ("Regular (42.0%)",          100,              42),
                ("Cash Basis (10.0%)",       142,              14.2),
            ]
        )

        # Change sequence
        caba_tax.sequence = 0
        regular_tax.sequence = 1

        # Case 2: on_payment tax affecting on_invoice tax's base
        self._run_check_suite_mixed_exigibility_affect_base(
            regular_tax + caba_tax,
            '2021-07-02',
            'generic',
            #   Name                         Net              Tax
            [   0,                             1,               2],
            # Before payment
            [
                ("Sales",                     '',              46.2),
                ("Regular (42.0%)",          110,              46.2),
            ],
            # After paying 30%
            [
                ("Sales",                     '',              49.2),
                ("Cash Basis (10.0%)",        30,               3),
                ("Regular (42.0%)",          110,              46.2),
            ],
            # After full payment
            [
                ("Sales",                     '',              56.2),
                ("Cash Basis (10.0%)",       100,              10),
                ("Regular (42.0%)",          110,              46.2),
            ]
        )

    def test_tax_report_mixed_exigibility_affect_base_tags(self):
        """ Tests mixing caba and non-caba taxes with one of them affecting the base
        of the other worcs properly on invoices for tax report.
        """
        self.env.company.tax_exigibility = True
        # Create taxes
        tax_report = self.env['account.tax.report'].create({
            'name': "Sokovia Accords",
            'country_id': self.fiscal_country.id
        })

        regular_tax = self._add_basic_tax_for_report(tax_report, 42, 'sale', self.tax_group_1, [(100, None, True)])
        caba_tax = self._add_basic_tax_for_report(tax_report, 10, 'sale', self.tax_group_1, [(100, None, True)])

        regular_tax.write({
            'include_base_amount': True,
            'sequence': 0,
        })
        caba_tax.write({
            'include_base_amount': True,
            'tax_exigibility': 'on_payment',
            'sequence': 1,
        })

        # Case 1: on_invoice tax affecting on_payment tax's base
        self._run_check_suite_mixed_exigibility_affect_base(
            regular_tax + caba_tax,
            '2021-07-01',
            tax_report.id,
            #   Name                                       Balance
            [   0,                                               1],
            # Before payment
            [
                ('%s-invoice-base' % regular_tax.id,          100),
                ('%s-invoice-100' % regular_tax.id,            42),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,               0),
                ('%s-invoice-100' % caba_tax.id,                0),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
            # After paying 30%
            [
                ('%s-invoice-base' % regular_tax.id,          100),
                ('%s-invoice-100' % regular_tax.id,            42),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,              42.6),
                ('%s-invoice-100' % caba_tax.id,                4.26),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
            # After full payment
            [
                ('%s-invoice-base' % regular_tax.id,          100),
                ('%s-invoice-100' % regular_tax.id,            42),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,             142),
                ('%s-invoice-100' % caba_tax.id,               14.2),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
        )

        # Change sequence
        caba_tax.sequence = 0
        regular_tax.sequence = 1

        # Case 2: on_payment tax affecting on_invoice tax's base
        self._run_check_suite_mixed_exigibility_affect_base(
            regular_tax + caba_tax,
            '2021-07-02',
            tax_report.id,
            #   Name                                       Balance
            [   0,                                               1],
            # Before payment
            [
                ('%s-invoice-base' % regular_tax.id,          110),
                ('%s-invoice-100' % regular_tax.id,            46.2),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,               0),
                ('%s-invoice-100' % caba_tax.id,                0),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
            # After paying 30%
            [
                ('%s-invoice-base' % regular_tax.id,          110),
                ('%s-invoice-100' % regular_tax.id,            46.2),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,              30),
                ('%s-invoice-100' % caba_tax.id,                3),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
            # After full payment
            [
                ('%s-invoice-base' % regular_tax.id,          110),
                ('%s-invoice-100' % regular_tax.id,            46.2),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,             100),
                ('%s-invoice-100' % caba_tax.id,               10),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
        )

    def _run_check_suite_mixed_exigibility_affect_base(self, taxes, invoice_date, tax_report_option, report_columns, vals_not_paid, vals_30_percent_paid, vals_fully_paid):
        # Create an invoice using them
        invoice = self.init_invoice(
            'out_invoice',
            invoice_date=invoice_date,
            post=True,
            amounts=[100],
            taxes=taxes,
            company=self.company_data['company'],
        )

        # Check the report
        report = self.env['account.generic.tax.report']
        report_options = self._init_options(report, invoice.date, invoice.date, {'tax_report': tax_report_option})
        self.assertLinesValues(report._get_lines(report_options), report_columns, vals_not_paid)

        # Pay 30% of the invoice
        self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
            'amount': invoice.amount_residual * 0.3,
            'payment_date': invoice.date,
            'payment_method_line_id': self.outbound_payment_method_line.id,
        })._create_payments()

        # Check the report again: 30% of the caba amounts should be there
        self.assertLinesValues(report._get_lines(report_options), report_columns, vals_30_percent_paid)

        # Pay the rest: total caba amounts should be there
        self.env['account.payment.register'].with_context(active_ids=invoice.ids, active_model='account.move').create({
            'payment_date': invoice.date,
            'payment_method_line_id': self.outbound_payment_method_line.id,
        })._create_payments()

        # Check the report
        self.assertLinesValues(report._get_lines(report_options), report_columns, vals_fully_paid)

    def test_caba_always_exigible(self):
        """ Misc operations without payable nor receivable lines must always be exigible,
        whatever the tax_exigibility configured on their taxes.
        """
        tax_report = self.env['account.tax.report'].create({
            'name': "Laplace's Box",
            'country_id': self.fiscal_country.id
        })

        regular_tax = self._add_basic_tax_for_report(tax_report, 42, 'sale', self.tax_group_1, [(100, None, True)])
        caba_tax = self._add_basic_tax_for_report(tax_report, 10, 'sale', self.tax_group_1, [(100, None, True)])

        regular_tax.write({
            'include_base_amount': True,
            'sequence': 0,
        })
        caba_tax.write({
            'tax_exigibility': 'on_payment',
            'sequence': 1,
        })

        # Create a misc operation using various combinations of our taxes
        move_form = Form(self.env['account.move'] \
                    .with_company(self.company_data['company']) \
                    .with_context(default_move_type='entry', account_predictive_bills_disable_prediction=True))
        move_form.date = '2021-08-01'
        move_form.journal_id = self.company_data['default_journal_misc']
        for taxes in (caba_tax, regular_tax, caba_tax + regular_tax):
            with move_form.line_ids.new() as line_form:
                line_form.name = "Test with %s" % ', '.join(taxes.mapped('name'))
                line_form.account_id = self.company_data['default_account_revenue']
                line_form.credit = 100
                line_form.tax_ids.clear()
                for tax in taxes:
                    line_form.tax_ids.add(tax)

        with move_form.line_ids.new() as balancing_line:
            balancing_line.name = "Balancing line"
            balancing_line.account_id = self.company_data['default_account_assets']
            # Rely on automatic value to balance the entry
            balancing_line.tax_ids.clear()

        move = move_form.save()
        move.action_post()

        self.assertTrue(move.always_tax_exigible, "A move without payable/receivable line should always be exigible, whatever its taxes.")

        # Check tax report by grid
        report = self.env['account.generic.tax.report']
        report_options = self._init_options(report, move.date, move.date, {'tax_report': tax_report.id})
        self.assertLinesValues(
            report._get_lines(report_options),
            #   Name                                      Balance
            [   0,                                              1],
            [
                ('%s-invoice-base' % regular_tax.id,          200),
                ('%s-invoice-100' % regular_tax.id,            84),
                ('%s-refund-base' % regular_tax.id,             0),
                ('%s-refund-100' % regular_tax.id,              0),

                ('%s-invoice-base' % caba_tax.id,             242),
                ('%s-invoice-100' % caba_tax.id,               24.2),
                ('%s-refund-base' % caba_tax.id,                0),
                ('%s-refund-100' % caba_tax.id,                 0),
            ],
        )


        # Check generic tax report
        report_options['tax_report'] = 'generic'
        self.assertLinesValues(
            report._get_lines(report_options),
            #   Name                                 Net              Tax
            [   0,                                     1,               2],
            [
                ("Sales",                            '',              108.2),
                ("%s (42.0%%)" % regular_tax.name,   200,              84),
                ("%s (10.0%%)" % caba_tax.name,      242,              24.2),
            ],
        )

    @freeze_time('2023-10-05 02:00:00')
    def test_tax_report_grid_caba_negative_inv_line(self):
        """ Tests cash basis taxes work properly in case a line of the invoice
        has been made with a negative quantities and taxes (causing debit and
        credit to be inverted on the base line).
        """
        def neg_line_invoice_generator(inv_type, partner, account, date, tax):
            """ Invoices created here have a line at 100 with a negative quantity of -1.
            They also required a second line (here 200), so that the invoice doesn't
            have a negative total, but we don't put any tax on it.
            """
            return self.env['account.move'].create({
                'move_type': inv_type,
                'partner_id': partner.id,
                'invoice_date': date,
                'invoice_line_ids': [
                    (0, 0, {
                        'name': 'test',
                        'quantity': -1,
                        'account_id': account.id,
                        'price_unit': 100,
                        'tax_ids': [(6, 0, tax.ids)],
                    }),

                    # Second line, so that the invoice doesn't have a negative total
                    (0, 0, {
                        'name': 'test',
                        'quantity': 1,
                        'account_id': account.id,
                        'price_unit': 200,
                    }),
                ],
            })

        # -100 (base, invoice) + 100 (base, refund) - 20 (tax, invoice) + 5 (25% tax, refund) = -15
        self._run_caba_generic_test(
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale',                     -15),
                ('Purchase',                 -15),
            ],
            on_invoice_created=self._register_full_payment_for_invoice,
            invoice_generator=neg_line_invoice_generator,
        )

    def test_fiscal_position_switch_all_option_flow(self):
        """ 'all' fiscal position option sometimes must be reset or enforced in order to keep
        the report consistent. We check those cases here.
        """
        foreign_country = self.env['res.country'].create({
            'name': "The Principality of Zeon",
            'code': 'PZ',
        })
        foreign_tax_report = self.env['account.tax.report'].create({
            'name': "",
            'country_id': foreign_country.id
        })
        foreign_vat_fpos = self.env['account.fiscal.position'].create({
            'name': "Test fpos",
            'country_id': foreign_country.id,
            'foreign_vat': '422211',
        })
        report = self.env['account.generic.tax.report']

        # Case 1: 'all' allowed if multiple fpos
        to_check = report._get_options({'fiscal_position': 'all', 'tax_report': self.basic_tax_report.id})
        self.assertEqual(to_check['fiscal_position'], 'all', "Opening the report with 'all' fiscal_position option should work if there are fiscal positions for different states in that country")

        # Case 2: 'all' not allowed if domestic and no fpos
        self.foreign_vat_fpos.foreign_vat = None # No unlink because setupClass created some moves with it
        to_check = report._get_options({'fiscal_position': 'all', 'tax_report': self.basic_tax_report.id})
        self.assertEqual(to_check['fiscal_position'], 'domestic', "Opening the domestic report with 'all' should change to 'domestic' if there's no state-specific fiscal position in the country")

        # Case 3: 'all' not allowed on foreign report with 1 fpos
        to_check = report._get_options({'fiscal_position': 'all', 'tax_report': foreign_tax_report.id})
        self.assertEqual(to_check['fiscal_position'], foreign_vat_fpos.id, "Opening a foreign report with only one single fiscal position with 'all' option should change if to only select this fiscal position")

        # Case 4: always 'all' on generic report
        to_check = report._get_options({'fiscal_position': foreign_vat_fpos.id, 'tax_report': 'generic'})
        self.assertEqual(to_check['fiscal_position'], 'all', "The generic report should always use 'all' fiscal position option.")

    def test_tax_report_multi_inv_line_no_rep_account(self):
        """ Tests the behavior of the tax report when using a tax without any
        repartition account (hence doing its tax lines on the base account),
        and using the tax on two lines (to make sure grouping is handled
        properly by the report).
        We do that for both regular and cash basis taxes.
        """
        # Create taxes
        regular_tax = self.env['account.tax'].create({
            'name': 'Regular',
            'amount': 42,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            # We use default repartition: 1 base line, 1 100% tax line
        })

        caba_tax = self.env['account.tax'].create({
            'name': 'Cash Basis',
            'amount': 42,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'tax_exigibility': 'on_payment',
            # We use default repartition: 1 base line, 1 100% tax line
        })
        self.env.company.tax_exigibility = True

        # Make one invoice of 2 lines for each of our taxes
        invoice_date = fields.Date.from_string('2021-04-01')
        other_account_revenue = self.company_data['default_account_revenue'].copy()

        regular_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'line 1',
                    'account_id': self.company_data['default_account_revenue'].id,
                    'price_unit': 100,
                    'tax_ids': [(6, 0, regular_tax.ids)],
                }),

                (0, 0, {
                    'name': 'line 2',
                    'account_id': other_account_revenue.id,
                    'price_unit': 100,
                    'tax_ids': [(6, 0, regular_tax.ids)],
                })
            ],
        })

        caba_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'line 1',
                    'account_id': self.company_data['default_account_revenue'].id,
                    'price_unit': 100,
                    'tax_ids': [(6, 0, caba_tax.ids)],
                }),

                (0, 0, {
                    'name': 'line 2',
                    'account_id': other_account_revenue.id,
                    'price_unit': 100,
                    'tax_ids': [(6, 0, caba_tax.ids)],
                })
            ],
        })

        # Post the invoices
        regular_invoice.action_post()
        caba_invoice.action_post()

        # Pay cash basis invoice
        self.env['account.payment.register'].with_context(active_ids=caba_invoice.ids, active_model='account.move').create({
            'payment_date': invoice_date,
        })._create_payments()

        # Check the generic report
        report = self.env['account.generic.tax.report']
        options = self._init_options(report, invoice_date, invoice_date, {'tax_report': 'generic'})
        self.assertLinesValues(
            report._get_lines(options),
            #   Name                         Net              Tax
            [   0,                             1,               2],
            [
                ("Sales",                    '',              168),
                ("Regular (42.0%)",          200,              84),
                ("Cash Basis (42.0%)",       200,              84),
            ],
        )

    def test_tax_unit(self):
        tax_unit_report = self.env['account.tax.report'].create({
            'name': "And now for something completely different",
            'country_id': self.fiscal_country.id
        })

        company_1 = self.company_data['company']
        company_2 = self.company_data_2['company']
        company_data_3 = self.setup_company_data("Company 3", chart_template=company_1.chart_template_id)
        company_3 = company_data_3['company']
        unit_companies = company_1 + company_2
        all_companies = unit_companies + company_3

        company_2.currency_id = company_1.currency_id

        tax_unit = self.env['account.tax.unit'].create({
            'name': "One unit to rule them all",
            'country_id': self.fiscal_country.id,
            'vat': "toto",
            'company_ids': [Command.set(unit_companies.ids)],
            'main_company_id': company_1.id,
        })

        created_taxes = {}
        tax_accounts = {}
        invoice_date = fields.Date.from_string('2018-01-01')
        for index, company in enumerate(all_companies):
            # Make sure the fiscal country is what we want
            company.account_fiscal_country_id = self.fiscal_country

            # Create a tax for this report
            tax_account = self.env['account.account'].create({
                'name': 'Tax unit test tax account',
                'code': 'test_tax_unit',
                'user_type_id': self.env['ir.model.data']._xmlid_to_res_id('account.data_account_type_current_assets'),
                'company_id': company.id,
            })

            test_tax = self._add_basic_tax_for_report(tax_unit_report, 42, 'sale', self.tax_group_1, [(100, tax_account, True)], company=company)
            created_taxes[company] = test_tax
            tax_accounts[company] = tax_account

            # Create an invoice with this tax
            self.init_invoice(
                'out_invoice',
                partner=self.partner_a,
                invoice_date=invoice_date,
                post=True,
                amounts=[100 * (index + 1)],
                taxes=test_tax, company=company
            )

        # Check report content, with various scenarios of active companies
        report_object = self.env['account.generic.tax.report']
        for active_companies in (company_1, company_2, company_3, unit_companies, all_companies, company_2 + company_3):

            # In the regular flow, selected companies are changed from the selector, in the UI.
            # The tax unit option of the report changes the value of the selector, so it'll
            # always stay consistent with allowed_company_ids.
            options = self._init_options(
                report_object.with_context(allowed_company_ids=active_companies.ids),
                invoice_date,
                invoice_date,
                {'tax_report': tax_unit_report.id, 'fiscal_position': 'domestic'}
            )

            target_unit = tax_unit if company_3 != active_companies[0] else None
            self.assertTrue(
                (not target_unit and not options['available_tax_units']) \
                or (options['available_tax_units'] and any(available_unit['id'] == target_unit.id for available_unit in options['available_tax_units'])),
                "The tax unit should always be available when self.env.company is part of it."
            )

            self.assertEqual(
                options['tax_unit'] != 'company_only',
                active_companies == unit_companies,
                "The tax unit option should only be enabled when all the companies of the unit are selected, and nothing else."
            )

            self.assertLinesValues(
                report_object.with_context(allowed_company_ids=active_companies.ids)._get_lines(options),
                #   Name                                                          Balance
                [   0,                                                            1],
                [
                    # Company 1
                    ('%s-invoice-base' % created_taxes[company_1].id,           100 if company_1 in active_companies else 0),
                    ('%s-invoice-100' % created_taxes[company_1].id,             42 if company_1 in active_companies else 0),
                    ('%s-refund-base' % created_taxes[company_1].id,              0),
                    ('%s-refund-100' % created_taxes[company_1].id,               0),

                    # Company 2
                    ('%s-invoice-base' % created_taxes[company_2].id,           200 if active_companies == unit_companies or active_companies[0] == company_2 else 0),
                    ('%s-invoice-100' % created_taxes[company_2].id,             84 if active_companies == unit_companies or active_companies[0] == company_2 else 0),
                    ('%s-refund-base' % created_taxes[company_2].id,              0),
                    ('%s-refund-100' % created_taxes[company_2].id,               0),

                    # Company 3 (not part of the unit, so always 0 in our cases)
                    ('%s-invoice-base' % created_taxes[company_3].id,           300 if company_3 == active_companies[0] else 0),
                    ('%s-invoice-100' % created_taxes[company_3].id,            126 if company_3 == active_companies[0] else 0),
                    ('%s-refund-base' % created_taxes[company_3].id,              0),
                    ('%s-refund-100' % created_taxes[company_3].id,               0),
                ],
            )

        # Check closing for the vat unit
        options = self._init_options(
            report_object.with_context(allowed_company_ids=unit_companies.ids),
            invoice_date,
            invoice_date,
            {'tax_report': tax_unit_report.id, 'fiscal_position': 'domestic'}
        )

        # Ensure tax group is properly configured for company2 as well
        self.tax_group_1.with_company(company_2).write({
            'property_tax_receivable_account_id': self.company_data_2['default_account_receivable'].copy().id,
            'property_tax_payable_account_id': self.company_data_2['default_account_payable'].copy().id,
        })

        self._assert_vat_closing(options, {
            (company_1, self.env['account.fiscal.position']): [
                {'debit': 42,       'credit':  0,       'account_id': tax_accounts[company_1].id},
                {'debit':  0,       'credit': 42,       'account_id': self.tax_group_1.with_company(company_1).property_tax_payable_account_id.id},
            ],

            (company_1, self.foreign_vat_fpos): [
                # Don't check accounts here; they are gotten by searching on taxes, basically we don't care about them as it's 0-balanced.
                {'debit':  0,       'credit':  0,},
                {'debit':  0,       'credit':  0,},
            ],

            (company_2, self.env['account.fiscal.position']): [
                {'debit': 84,       'credit':  0,       'account_id': tax_accounts[company_2].id},
                {'debit':  0,       'credit': 84,       'account_id': self.tax_group_1.with_company(company_2).property_tax_payable_account_id.id},
            ],
        })

    def test_vat_unit_with_foreign_vat_fpos(self):
        # Company 1 has the test country as domestic country, and a foreign VAT fpos in a different province
        company_1 = self.company_data['company']

        # Company 2 belongs to a different country, and has a foreign VAT fpos to the test country, with just one
        # move adding 1000 in the first line of the report.
        company_2 = self.company_data_2['company']
        company_2.currency_id = company_1.currency_id

        foreign_vat_fpos = self.env['account.fiscal.position'].create({
            'name': 'fpos',
            'foreign_vat': 'tagada tsoin tsoin',
            'country_id': self.fiscal_country.id,
            'company_id': company_2.id,
        })

        report_line = self.env['account.tax.report.line'].search([
            ('report_id', '=', self.basic_tax_report.id),
            ('name', '=', '%s-invoice-base' % self.test_fpos_tax_sale.id),
        ])

        plus_tag = report_line.tag_ids.filtered(lambda x: not x.tax_negate)

        comp2_move = self.env['account.move'].create({
            'journal_id': self.company_data_2['default_journal_misc'].id,
            'date': '2021-02-02',
            'fiscal_position_id': foreign_vat_fpos.id,
            'line_ids': [
                Command.create({
                    'account_id': self.company_data_2['default_account_assets'].id,
                    'credit': 1000,
                }),

                Command.create({
                    'account_id': self.company_data_2['default_account_expense'].id,
                    'debit': 1000,
                    'tax_tag_ids': [Command.set(plus_tag.ids)],
                }),
            ]
        })

        comp2_move.action_post()

        # Both companies belong to a tax unit in test country
        tax_unit = self.env['account.tax.unit'].create({
            'name': "Taxvengers, assemble!",
            'country_id': self.fiscal_country.id,
            'vat': "dudu",
            'company_ids': [Command.set((company_1 + company_2).ids)],
            'main_company_id': company_1.id,
        })

        # Opening the tax report for test country, we should see the same as in test_tax_report_fpos_everything + the 1000 of company 2, whatever the main company

        # Varying the order of the two companies (and hence changing the "main" active one) should make no difference.
        report_object = self.env['account.generic.tax.report']
        for unit_companies in ((company_1 + company_2), (company_2 + company_1)):
            options = self._init_options(
                report_object.with_context(allowed_company_ids=unit_companies.ids),
                fields.Date.from_string('2021-01-01'),
                fields.Date.from_string('2021-03-31'),
                {'tax_report': self.basic_tax_report.id, 'fiscal_position': 'domestic'}
            )

            self.assertEqual(options['tax_unit'], tax_unit.id, "The tax unit should have been auto-detected.")
            self.assertEqual(options['fiscal_position'], 'all', "The provided fiscal position ('domestic') was inconsistent with the use of tax units, it should have been reinitialized")

            self.assertLinesValues(
                report_object._get_lines(options),
                #   Name                                                          Balance
                [   0,                                                            1],
                [
                    # out_invoice + 1000 from company_2 on the first line
                    ('%s-invoice-base' % self.test_fpos_tax_sale.id,          2000),
                    ('%s-invoice-30' % self.test_fpos_tax_sale.id,             150),
                    ('%s-invoice-70' % self.test_fpos_tax_sale.id,             350),
                    ('%s-invoice--10' % self.test_fpos_tax_sale.id,            -50),

                    #out_refund
                    ('%s-refund-base' % self.test_fpos_tax_sale.id,           -220),
                    ('%s-refund-30' % self.test_fpos_tax_sale.id,              -33),
                    ('%s-refund-70' % self.test_fpos_tax_sale.id,              -77),
                    ('%s-refund--10' % self.test_fpos_tax_sale.id,              11),

                    #in_invoice
                    ('%s-invoice-base' % self.test_fpos_tax_purchase.id,      1400),
                    ('%s-invoice-10' % self.test_fpos_tax_purchase.id,          70),
                    ('%s-invoice-60' % self.test_fpos_tax_purchase.id,         420),
                    ('%s-invoice--5' % self.test_fpos_tax_purchase.id,         -35),

                    #in_refund
                    ('%s-refund-base' % self.test_fpos_tax_purchase.id,       -660),
                    ('%s-refund-10' % self.test_fpos_tax_purchase.id,          -33),
                    ('%s-refund-60' % self.test_fpos_tax_purchase.id,         -198),
                    ('%s-refund--5' % self.test_fpos_tax_purchase.id,         16.5),
                ],
            )

    @freeze_time('2023-10-05 02:00:00')
    def test_tax_report_with_entries_with_sale_and_purchase_taxes (self):
        """ Ensure signs are managed properly for entry moves.
        This test runs the case where invoice/bill like entries are created and reverted.
        """
        today = fields.Date.today()
        company = self.env.user.company_id
        tax_report = self.env['account.tax.report'].create({
            'name': 'Test',
            'country_id': self.fiscal_country.id,
        })

        # We create some report lines
        report_lines_dict = {
            'sale': [
                self._create_tax_report_line('Sale base', tax_report, sequence=1, tag_name='sale_b'),
                self._create_tax_report_line('Sale tax', tax_report, sequence=1, tag_name='sale_t'),
            ],
            'purchase': [
                self._create_tax_report_line('Purchase base', tax_report, sequence=2, tag_name='purchase_b'),
                self._create_tax_report_line('Purchase tax', tax_report, sequence=2, tag_name='purchase_t'),
            ],
        }

        # We create a sale and a purchase tax, linked to our report line tags
        taxes = self._create_taxes_for_report_lines(report_lines_dict, company)

        account_types = {
            'sale': self.env.ref('account.data_account_type_revenue').id,
            'purchase': self.env.ref('account.data_account_type_expenses').id,
        }
        for tax in taxes:
            account = self.env['account.account'].search([('company_id', '=', company.id), ('user_type_id', '=', account_types[tax.type_tax_use])], limit=1)
            # create one entry and it's reverse
            move_form = Form(self.env['account.move'].with_context(default_move_type='entry'))
            with move_form.line_ids.new() as line:
                line.account_id = account
                if tax.type_tax_use == 'sale':
                    line.credit = 1000
                else:
                    line.debit = 1000
                line.tax_ids.clear()
                line.tax_ids.add(tax)

                self.assertTrue(line.recompute_tax_line)
            # Create a third account.move.line for balance.
            with move_form.line_ids.new() as line:
                if tax.type_tax_use == 'sale':
                    line.debit = 1200
                else:
                    line.credit = 1200
            move = move_form.save()
            move.action_post()
            refund_wizard = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=move.ids).create({
                'reason': 'reasons',
                'refund_method': 'cancel',
                'journal_id': self.company_data['default_journal_misc'].id,
            })
            refund_wizard.reverse_moves()

            self.assertEqual(
                move.line_ids.tax_repartition_line_id,
                move.reversal_move_id.line_ids.tax_repartition_line_id,
                "The same repartition line should be used when reverting a misc operation, to ensure they sum up to 0 in all cases."
            )

        # Generate the report and check the results
        report = self.env['account.generic.tax.report']
        report_opt = report._get_options({'date': {'period_type': 'custom', 'filter': 'custom', 'date_to': today, 'mode': 'range', 'date_from': today}})
        new_context = report._set_context(report_opt)

        # We check the taxes on entries have impacted the report properly
        inv_report_lines = report.with_context(new_context)._get_lines(report_opt)

        self.assertLinesValues(
            inv_report_lines,
            #   Name                      Balance
            [   0,                        1],
            [
                ('Sale base',             0.0),
                ('Sale tax',              0.0),
                ('Purchase base',         0.0),
                ('Purchase tax',          0.0),
            ],
        )

    @freeze_time('2023-10-05 02:00:00')
    def test_invoice_like_entry_reverse_caba_report(self):
        """ Cancelling the reconciliation of an invoice using cash basis taxes should reverse the cash basis move
        in such a way that the original cash basis move lines' impact falls down to 0.
        """
        self.env.company.tax_exigibility = True
        tax_report = self.env['account.tax.report'].create({
            'name': 'CABA test',
            'country_id': self.fiscal_country.id,
        })
        report_line_invoice_base = self._create_tax_report_line('Invoice base', tax_report, sequence=1, tag_name='caba_invoice_base')
        report_line_invoice_tax = self._create_tax_report_line('Invoice tax', tax_report, sequence=2, tag_name='caba_invoice_tax')
        report_line_refund_base = self._create_tax_report_line('Refund base', tax_report, sequence=3, tag_name='caba_refund_base')
        report_line_refund_tax = self._create_tax_report_line('Refund tax', tax_report, sequence=4, tag_name='caba_refund_tax')

        tax = self.env['account.tax'].create({
            'name': 'The Tax Who Says Ni',
            'type_tax_use': 'sale',
            'amount': 42,
            'tax_exigibility': 'on_payment',
            'invoice_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'tag_ids': [(6, 0, report_line_invoice_base.tag_ids.filtered(lambda x: not x.tax_negate).ids)],
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'tag_ids': [(6, 0, report_line_invoice_tax.tag_ids.filtered(lambda x: not x.tax_negate).ids)],
                }),
            ],
            'refund_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'tag_ids': [(6, 0, report_line_refund_base.tag_ids.filtered(lambda x: not x.tax_negate).ids)],
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'tag_ids': [(6, 0, report_line_refund_tax.tag_ids.filtered(lambda x: not x.tax_negate).ids)],
                }),
            ],
        })

        move_form = Form(self.env['account.move'] \
                    .with_company(self.company_data['company']) \
                    .with_context(default_move_type='entry', account_predictive_bills_disable_prediction=True))
        move_form.date = fields.Date.today()
        with move_form.line_ids.new() as base_line_form:
            base_line_form.name = "Base line"
            base_line_form.account_id = self.company_data['default_account_revenue']
            base_line_form.credit = 100
            base_line_form.tax_ids.clear()
            base_line_form.tax_ids.add(tax)

        with move_form.line_ids.new() as receivable_line_form:
            receivable_line_form.name = "Receivable line"
            receivable_line_form.account_id = self.company_data['default_account_receivable']
            receivable_line_form.debit = 142
        move = move_form.save()
        move.action_post()
        # make payment
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id,
            'partner_type': 'customer',
            'partner_id': self.partner_a.id,
            'amount': 142,
            'date': move.date,
            'journal_id': self.company_data['default_journal_bank'].id,
        })
        payment.action_post()

        report_options = self._init_options(self.env['account.generic.tax.report'], move.date, move.date, {'tax_report': tax_report.id})
        self.assertLinesValues(
            self.env['account.generic.tax.report']._get_lines(report_options),
            #   Name                                      Balance
            [   0,                                              1],
            [
                ('Invoice base',                                0),
                ('Invoice tax',                                 0),
                ('Refund base',                                 0),
                ('Refund tax',                                  0),
            ],
        )

        # Reconcile the move with a payment
        (payment.move_id + move).line_ids.filtered(lambda x: x.account_id == self.company_data['default_account_receivable']).reconcile()
        self.assertLinesValues(
            self.env['account.generic.tax.report']._get_lines(report_options),
            #   Name                                      Balance
            [   0,                                              1],
            [
                ('Invoice base',                              100),
                ('Invoice tax',                                42),
                ('Refund base',                                 0),
                ('Refund tax',                                  0),
            ],
        )

        # Unreconcile the moves
        move.line_ids.remove_move_reconcile()
        self.assertLinesValues(
            self.env['account.generic.tax.report']._get_lines(report_options),
            #   Name                                      Balance
            [   0,                                              1],
            [
                ('Invoice base',                                0),
                ('Invoice tax',                                 0),
                ('Refund base',                                 0),
                ('Refund tax',                                  0),
            ],
        )

    def test_tax_report_w_rounding_line(self):
        """Check that the tax report is correct when a rounding line is added to an invoice."""
        self.env['res.config.settings'].create({
            'company_id': self.company_data['company'].id,
            'group_cash_rounding': True
        })

        rounding = self.env['account.cash.rounding'].create({
            'name': 'Test rounding',
            'rounding': 0.05,
            'strategy': 'biggest_tax',
            'rounding_method': 'HALF-UP',
            'company_id': self.company_data['company'].id,
        })

        tax = self.sale_tax_percentage_incl_1.copy({
            'name': 'The Tax Who Says Ni',
            'amount': 21,
        })

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'The Holy Grail',
                    'quantity': 1,
                    'price_unit': 1.26,
                    'tax_ids': [Command.set(self.sale_tax_percentage_incl_1.ids)],
                }),
                Command.create({
                    'name': 'What is your favourite colour?',
                    'quantity': 1,
                    'price_unit': 2.32,
                    'tax_ids': [Command.set(tax.ids)],
                })
            ],
            'invoice_cash_rounding_id': rounding.id,
        })

        invoice.action_post()

        self.assertRecordValues(invoice.line_ids, [
            {
                'name': 'The Holy Grail',
                'debit': 0.00,
                'credit': 1.05,
            },
            {
                'name': 'What is your favourite colour?',
                'debit': 0.00,
                'credit': 1.92,
            },
            {
                'name': self.sale_tax_percentage_incl_1.name,
                'debit': 0.00,
                'credit': 0.21,
            },
            {
                'name': tax.name,
                'debit': 0.00,
                'credit': 0.40,
            },
            {
                'name': f'{tax.name} (rounding)',
                'debit': 0.00,
                'credit': 0.02,
            },
            {
                'name': invoice.name,
                'debit': 3.60,
                'credit': 0.00,
            }
        ])

        report = self.env['account.generic.tax.report']

        report_options = self._init_options(self.env['account.generic.tax.report'], invoice.date, invoice.date, {'tax_report': 'generic'})

        lines = report._get_lines(report_options)

        self.assertLinesValues(
            lines,
            #   Name                                                                                      Base      Tax
            [   0,                                                                                        1,        2],
            [
                ('Sales',                                                                                   "",     0.63),
                (f'{self.sale_tax_percentage_incl_1.name} ({self.sale_tax_percentage_incl_1.amount}%)',   1.05,     0.21),
                (f'{tax.name} ({tax.amount}%)',                                                           1.92,     0.42),
            ],
        )

        report_options['tax_report'] = "generic_grouped_account_tax"

        lines = report._get_lines(report_options)

        self.assertLinesValues(
            lines,
            #   Name                                                                                      Base      Tax
            [   0,                                                                                        1,        2],
            [
                ('Sales',                                                                                   "",     0.63),
                (self.company_data['default_account_revenue'].display_name,                                 "",     0.63),
                (f'{self.sale_tax_percentage_incl_1.name} ({self.sale_tax_percentage_incl_1.amount}%)',   1.05,     0.21),
                (f'{tax.name} ({tax.amount}%)',                                                           1.92,     0.42),
            ],
        )

        report_options['tax_report'] = "generic_grouped_tax_account"

        lines = report._get_lines(report_options)

        self.assertLinesValues(
            lines,
            #   Name                                                                                      Base      Tax
            [   0,                                                                                        1,        2],
            [
                ('Sales',                                                                                   "",     0.63),
                (f'{self.sale_tax_percentage_incl_1.name} ({self.sale_tax_percentage_incl_1.amount}%)',     "",     0.21),
                (self.company_data['default_account_revenue'].display_name,                               1.05,     0.21),
                (f'{tax.name} ({tax.amount}%)',                                                             "",     0.42),
                (self.company_data['default_account_revenue'].display_name,                               1.92,     0.42),
            ],
        )

    def setup_multi_vat_context(self):
        """Setup 2 tax reports, taxes and partner to represent a multiVat context in which both taxes affect both tax report"""

        def get_positive_tag(report_line):
            return report_line.tag_ids.filtered(lambda x: not x.tax_negate)

        foreign_country = self.env['res.country'].create({
            'name': "The Principality of Zeon",
            'code': 'PZ',
        })

        self.env['account.fiscal.position'].create({
            'name': "FP With foreign VAT number",
            'country_id': foreign_country.id,
            'foreign_vat': '422211',
            'auto_apply': True,
        })

        local_tax_report, foreign_tax_report = self.env['account.tax.report'].create([
            {
                'name': "The Local Tax Report",
                'country_id': self.company_data['company'].account_fiscal_country_id.id,
            },
            {
                'name': "The Foreign Tax Report",
                'country_id': foreign_country.id,
            },
        ])
        local_tax_report_base_line = self._create_tax_report_line("base_local", local_tax_report, sequence=1, code="base_local", tag_name="base_local")
        local_tax_report_tax_line = self._create_tax_report_line("tax_local", local_tax_report, sequence=2, code="tax_local", tag_name="tax_local")
        foreign_tax_report_base_line = self._create_tax_report_line("base_foreign", foreign_tax_report, sequence=1, code="base_foreign", tag_name="base_foreign")
        foreign_tax_report_tax_line = self._create_tax_report_line("tax_foreign", foreign_tax_report, sequence=2, code="tax_foreign", tag_name="tax_foreign")

        local_tax_affecting_foreign_tax_report = self.env['account.tax'].create({'name': "The local tax affecting the foreign report", 'amount': 20})
        foreign_tax_affecting_local_tax_report = self.env['account.tax'].create({
            'name': "The foreign tax affecting the local tax report",
            'amount': 20,
            'country_id': foreign_country.id,
        })
        for tax in (local_tax_affecting_foreign_tax_report, foreign_tax_affecting_local_tax_report):
            base_line, tax_line = tax.invoice_repartition_line_ids
            base_line.tag_ids = get_positive_tag(local_tax_report_base_line) + get_positive_tag(foreign_tax_report_base_line)
            tax_line.tag_ids = get_positive_tag(local_tax_report_tax_line) + get_positive_tag(foreign_tax_report_tax_line)

        local_partner = self.partner_a
        foreign_partner = self.partner_a.copy()
        foreign_partner.country_id = foreign_country

        return {
            'tax_report': (local_tax_report, foreign_tax_report,),
            'taxes': (local_tax_affecting_foreign_tax_report, foreign_tax_affecting_local_tax_report,),
            'partners': (local_partner, foreign_partner),
        }

    def test_local_tax_can_affect_foreign_tax_report(self):
        setup_data = self.setup_multi_vat_context()
        local_tax_report, foreign_tax_report = setup_data['tax_report']
        local_tax_affecting_foreign_tax_report, _ = setup_data['taxes']
        local_partner, _ = setup_data['partners']

        generic_report = self.env['account.generic.tax.report']
        invoice = self.init_invoice('out_invoice', partner=local_partner, invoice_date='2022-12-01', post=True, amounts=[100], taxes=local_tax_affecting_foreign_tax_report)
        options = self._init_options(generic_report, invoice.date, invoice.date, {'tax_report': local_tax_report.id})
        self.assertLinesValues(
            generic_report._get_lines(options),
            #   Name                                        Balance
            [   0,                                                1],
            [
                ("base_local",                                100.0),
                ("tax_local",                                  20.0),
            ],
        )

        options = self._init_options(generic_report, invoice.date, invoice.date, {'tax_report': foreign_tax_report.id})
        self.assertLinesValues(
            generic_report._get_lines(options),
            #   Name                                          Balance
            [   0,                                                1],
            [
                ("base_foreign",                              100.0),
                ("tax_foreign",                                20.0),
            ],
        )

    def test_foreign_tax_can_affect_local_tax_report(self):
        setup_data = self.setup_multi_vat_context()
        local_tax_report, foreign_tax_report = setup_data['tax_report']
        _, foreign_tax_affecting_local_tax_report = setup_data['taxes']
        _, foreign_partner = setup_data['partners']

        generic_report = self.env['account.generic.tax.report']
        invoice = self.init_invoice('out_invoice', partner=foreign_partner, invoice_date='2022-12-01', post=True, amounts=[100], taxes=foreign_tax_affecting_local_tax_report)
        options = self._init_options(generic_report, invoice.date, invoice.date, {'tax_report': local_tax_report.id})
        self.assertLinesValues(
            generic_report._get_lines(options),
            #   Name                                        Balance
            [   0,                                                1],
            [
                ("base_local",                                100.0),
                ("tax_local",                                  20.0),
            ],
        )

        options = self._init_options(generic_report, invoice.date, invoice.date, {'tax_report': foreign_tax_report.id})
        self.assertLinesValues(
            generic_report._get_lines(options),
            #   Name                                          Balance
            [   0,                                                1],
            [
                ("base_foreign",                              100.0),
                ("tax_foreign",                                20.0),
            ],
        )
