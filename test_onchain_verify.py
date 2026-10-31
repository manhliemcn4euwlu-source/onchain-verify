# -*- coding: utf-8 -*-
"""onchain_verify 双源核验门禁(全 mock, 不打网络)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import onchain_verify as O

TX = '0x' + 'ab' * 32
TO = '0x' + '11' * 20
TOKEN = '0x' + '22' * 20
OTHER = '0x' + '33' * 20


def log(to=TO, value=100, token=TOKEN):
    return {'address': token,
            'topics': [O.TRANSFER,
                       '0x' + '44' * 32,
                       '0x' + to[2:].rjust(64, '0')],
            'data': hex(value)}


def receipt(status='0x1', block='0x10', to=TO, value=100, token=TOKEN):
    return {'blockNumber': block, 'status': status, 'from': OTHER, 'logs': [log(to, value, token)]}


class TestVerify(unittest.TestCase):
    def _patch(self, first, second):
        def fake(url, method, params, timeout=20):
            if url == O.PROVIDERS[0][1]:
                return first
            return second
        return mock.patch.object(O, '_rpc', fake)

    def test_bad_hash(self):
        r = O.verify('nope')
        self.assertEqual(r['verdict'], 'unverifiable')

    def test_two_sources_agree_pass(self):
        with self._patch(receipt(), receipt()):
            r = O.verify(TX, expect_to=TO, expect_value='100', token=TOKEN)
        self.assertEqual(r['verdict'], 'pass')
        self.assertTrue(r['cross_checked'])

    def test_single_source_is_not_cross_checked(self):
        def fake(url, method, params, timeout=20):
            if url == O.PROVIDERS[0][1]:
                raise RuntimeError('timeout')
            return receipt()
        with mock.patch.object(O, '_rpc', fake):
            r = O.verify(TX, expect_to=TO, expect_value='100')
        self.assertEqual(r['verdict'], 'pass')
        self.assertFalse(r['cross_checked'])
        self.assertFalse(r['sources']['blastapi']['ok'])

    def test_no_source_is_unverifiable(self):
        with mock.patch.object(O, '_rpc', mock.Mock(side_effect=RuntimeError('down'))):
            r = O.verify(TX)
        self.assertEqual(r['verdict'], 'unverifiable')
        self.assertIn('not evidence', r['reason'])

    def test_sources_disagree_is_unverifiable(self):
        with self._patch(receipt(block='0x10'), receipt(block='0x11')):
            r = O.verify(TX)
        self.assertEqual(r['verdict'], 'unverifiable')
        self.assertIn('disagree', r['reason'])

    def test_wrong_recipient_is_mismatch(self):
        with self._patch(receipt(), receipt()):
            r = O.verify(TX, expect_to='0x' + '99' * 20)
        self.assertEqual(r['verdict'], 'mismatch')

    def test_wrong_value_is_mismatch(self):
        with self._patch(receipt(), receipt()):
            r = O.verify(TX, expect_to=TO, expect_value='999')
        self.assertEqual(r['verdict'], 'mismatch')

    def test_no_assertions_is_pass_when_sources_agree(self):
        """2026-10-31: 没传断言时旧逻辑回 unverifiable, 但双源一致读到收据本身就是成功核验。"""
        with self._patch(receipt(), receipt()):
            r = O.verify(TX)
        self.assertEqual(r['verdict'], 'pass')
        self.assertTrue(r['cross_checked'])
        self.assertEqual(r['checks'], [])

    def test_wrong_token_is_mismatch(self):
        with self._patch(receipt(), receipt()):
            r = O.verify(TX, token='0x' + '77' * 20)
        self.assertEqual(r['verdict'], 'mismatch')


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()
