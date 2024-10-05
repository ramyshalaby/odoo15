# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ctypes
import datetime
import logging
from pathlib import Path
from time import sleep
from queue import Queue

from odoo.addons.hw_drivers.driver import Driver
from odoo.addons.hw_drivers.event_manager import event_manager

_logger = logging.getLogger(__name__)

easyCTEPPath = Path(__file__).parent.parent / 'lib/ctep/libeasyctep.so'

if easyCTEPPath.exists():
    # Load library
    easyCTEP = ctypes.CDLL(easyCTEPPath)


# All the terminal errors can be found in the section "Codes d'erreur" here:
# https://help.winbooks.be/pages/viewpage.action?pageId=64455643#LiaisonversleterminaldepaiementBanksysenTCP/IP-Codesd'erreur
TERMINAL_ERRORS = {
    '1802': 'Terminal is busy',
    '1803': 'Timeout expired',
    '2629': 'User cancellation',
}

# Manually cancelled by cashier, do not show these errors
IGNORE_ERRORS = [
    '2628', # External Equipment Cancellation
    '2630', # Device Cancellation
]


class WorldlineDriver(Driver):
    connection_type = 'ctep'

    DELAY_TIME_BETWEEN_TRANSACTIONS = 5  # seconds

    def __init__(self, identifier, device):
        super(WorldlineDriver, self).__init__(identifier, device)
        self.device_type = 'payment'
        self.device_connection = 'network'
        self.device_name = 'Worldline terminal %s' % self.device_identifier
        self.device_manufacturer = 'Worldline'
        self.cid = None
        self.owner = None
        self.queue_actions = Queue()
        self.terminal_busy = False

        self._actions.update({
            '': self._action_default,
        })
        self.next_transaction_min_dt = datetime.datetime.min

    @classmethod
    def supported(cls, device):
        # All devices with connection_type CTEP are supported
        return True

    def _action_default(self, data):
        data_message_type = data.get('messageType')
        data['owner'] = self.data.get('owner')
        _logger.debug('_action_default %s %s', data_message_type, data)
        if data_message_type in ['Transaction', 'LastTransactionStatus']:
            if self.terminal_busy:
                self.send_status(error="The terminal is currently busy. Try again later.", request_data=data)
            else:
                self.terminal_busy = True
                self.queue_actions.put(data)
        elif data['messageType'] == 'Cancel':
            self.cancelTransaction(data)

    def run(self):
        while True:
            # If the queue is empty, the call of "get" will block and wait for it to get an item
            action = self.queue_actions.get()
            action_type = action.get('messageType')
            _logger.debug("Starting next action in queue: %s", action_type)
            if action_type == 'Transaction':
                self.processTransaction(action)
            elif action_type == 'LastTransactionStatus':
                self.lastTransactionStatus(action)
            self.terminal_busy = False

    def _check_transaction_delay(self):
        # After a payment has been processed, the display on the terminal still shows some
        # information for about 4-5 seconds. No request can be processed during this period.
        delay_diff = (self.next_transaction_min_dt - datetime.datetime.now()).total_seconds()
        if delay_diff > 0:
            if delay_diff > self.DELAY_TIME_BETWEEN_TRANSACTIONS:
                # Theoretically not possible, but to avoid sleeping for ages, we cap the value
                _logger.warning('Transaction delay difference is too high %.2f force set as default', delay_diff)
                delay_diff = self.DELAY_TIME_BETWEEN_TRANSACTIONS
            _logger.info('Previous transaction is too recent, will sleep for %.2f seconds', delay_diff)
            sleep(delay_diff)

    def processTransaction(self, transaction):
        if transaction['amount'] <= 0:
            return self.send_status(error='The terminal cannot process negative or null transactions.', request_data=transaction)

        # Force to wait before starting the transaction if necessary
        self._check_transaction_delay()
        # Notify transaction start
        self.send_status(stage='WaitingForCard', request_data=transaction)

        # Transaction
        merchant_receipt = ctypes.create_string_buffer(500)
        customer_receipt = ctypes.create_string_buffer(500)
        card = ctypes.create_string_buffer(20)
        error_code = ctypes.create_string_buffer(10)
        transaction_id = transaction['TransactionID']
        transaction_amount = transaction['amount'] / 100
        transaction_action_identifier = transaction['actionIdentifier']
        _logger.info('start transaction #%d amount: %f action_identifier: %d', transaction_id, transaction_amount, transaction_action_identifier)
        result = easyCTEP.startTransaction(
            ctypes.byref(self.dev),
            ctypes.c_char_p(str(transaction_amount).encode('utf-8')),
            ctypes.c_char_p(str(transaction_id).encode('utf-8')),
            ctypes.c_ulong(transaction_action_identifier),
            ctypes.byref(merchant_receipt),
            ctypes.byref(customer_receipt),
            ctypes.byref(card),
            ctypes.byref(error_code),
        )
        _logger.debug('finished transaction #%d with result %d', transaction_id, result)

        self.next_transaction_min_dt = datetime.datetime.now() + datetime.timedelta(seconds=self.DELAY_TIME_BETWEEN_TRANSACTIONS)

        if result == 1:
            # Transaction successful
            self.send_status(
                response='Approved',
                ticket=customer_receipt.value,
                ticket_merchant=merchant_receipt.value,
                card=card.value,
                transaction_id=transaction['actionIdentifier'],
                request_data=transaction,
            )
        elif result == 0:
            error_code = error_code.value.decode('utf-8')
            # Transaction failed
            if error_code not in IGNORE_ERRORS:
                error_msg = '%s (Error code: %s)' % (TERMINAL_ERRORS.get(error_code, 'Transaction was not processed correctly'), error_code)
                logging.info(error_msg)
                self.send_status(error=error_msg, request_data=transaction)
            # Transaction was cancelled
            else:
                self.send_status(stage='Cancel', request_data=transaction)
        elif result == -1:
            # Terminal disconnection, check status manually
            self.send_status(disconnected=True, request_data=transaction)

    def cancelTransaction(self, transaction):
        # Force to wait before starting the transaction if necessary
        self._check_transaction_delay()
        self.send_status(stage='waitingCancel', request_data=transaction)

        error_code = ctypes.create_string_buffer(10)
        _logger.info("cancel transaction request")
        result = easyCTEP.abortTransaction(ctypes.byref(self.dev), ctypes.byref(error_code))
        _logger.debug("end cancel transaction request")

        if not result:
            error_code = error_code.value.decode('utf-8')
            error_msg = '%s (Error code: %s)' % (TERMINAL_ERRORS.get(error_code, 'Transaction could not be cancelled'), error_code)
            _logger.info(error_msg)
            self.send_status(stage='Cancel', error=error_msg, request_data=transaction)

    def lastTransactionStatus(self, request_data):
        action_identifier = ctypes.c_ulong()
        amount = ctypes.c_double()
        time = ctypes.create_string_buffer(20)
        error_code = ctypes.create_string_buffer(10)
        _logger.info("last transaction status request")
        result = easyCTEP.lastTransactionStatus(ctypes.byref(self.dev), ctypes.byref(action_identifier), ctypes.byref(amount), ctypes.byref(time), ctypes.byref(error_code))
        _logger.debug("end last transaction status request")

        if result:
            self.send_status(
                value={
                    'action_identifier': action_identifier.value,
                    'amount': amount.value,
                    'time': time.value,
                },
                request_data=request_data,
            )
        else:
            error_code = error_code.value.decode('utf-8')
            error_msg = '%s (Error code: %s)' % (TERMINAL_ERRORS.get(error_code, 'Last Transaction Status request failed'), error_code)
            self.send_status(error=error_msg, request_data=request_data)

    def send_status(self, value='', response=False, stage=False, ticket=False, ticket_merchant=False, card=False, transaction_id=False, error=False, disconnected=False, request_data=False):
        self.data = {
            'value': value,
            'Stage': stage,
            'Response': response,
            'Ticket': ticket,
            'TicketMerchant': ticket_merchant,
            'Card': card,
            'PaymentTransactionID': transaction_id,
            'Error': error,
            'Disconnected': disconnected,
            'owner': request_data.get('owner'),
            'cid': request_data.get('cid'),
        }
        # TODO: add `stacklevel=2` in image with python version > 3.8
        _logger.debug('send_status data: %s', self.data, stack_info=True)
        event_manager.device_changed(self)
