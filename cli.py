#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flapjax-forensics: verify a BSC transaction against two independent RPC providers.

Usage:
  python3 cli.py verify <tx_hash> [--to 0x..] [--value <smallest_unit>] [--token 0x..]
  python3 cli.py treasury [--token 0x..] [--holder 0x..]

Exit codes: 0 pass, 1 mismatch, 2 unverifiable, 3 bad usage.
"""
import argparse
import json
import sys
import urllib.request

import onchain_verify as O

TREASURY = '0x7C34E9e21eE28A49Ff0b84B61774119E6633359f'
FJ = '0x90c8889f428F9Ebb77BF8f15CAD3a50a9aC680df'


def _call(url, data):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call',
                       'params': [{'to': FJ, 'data': data}, 'latest']}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def balance_of(addr, token=FJ):
    """Read balanceOf from two providers; both must agree."""
    data = '0x70a08231' + addr.lower()[2:].rjust(64, '0')
    reads = {}
    for name, url in O.PROVIDERS:
        try:
            reads[name] = int(_call(url, data)['result'], 16)
        except Exception as e:
            reads[name] = None
    vals = [v for v in reads.values() if v is not None]
    agree = len(vals) == 2 and vals[0] == vals[1]
    return {'balance_raw': vals[0] if vals else None, 'agree': agree, 'sources': reads}


def cmd_verify(a):
    v = O.verify(a.tx, expect_to=a.to, expect_value=a.value, token=a.token)
    print(json.dumps(v, indent=1))
    return {'pass': 0, 'mismatch': 1}.get(v.get('verdict'), 2)


def cmd_treasury(a):
    r = balance_of(a.holder or TREASURY)
    out = {'holder': a.holder or TREASURY, 'token': FJ}
    out.update(r)
    if r['balance_raw'] is not None:
        out['balance_fj'] = str(r['balance_raw'] / 10 ** 18)
    print(json.dumps(out, indent=1))
    return 0 if r['agree'] else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('verify', help='verify one transaction')
    v.add_argument('tx')
    v.add_argument('--to')
    v.add_argument('--value')
    v.add_argument('--token')
    v.set_defaults(fn=cmd_verify)
    t = sub.add_parser('treasury', help='read a FJ balance from two providers')
    t.add_argument('--token')
    t.add_argument('--holder')
    t.set_defaults(fn=cmd_treasury)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
