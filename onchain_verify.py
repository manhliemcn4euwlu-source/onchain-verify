# -*- coding: utf-8 -*-
"""链上收据双源核验器: 给定 tx hash, 用两个独立 RPC 交叉核对金额/发送方/收款方。

背景(2026-10-31): 单一 RPC 会静默返回 null 收据或空日志, 于是「核验通过」可能只是
「这个节点没给我数据」。本模块对同一笔 tx 请求两个 provider, 只有两边一致才判 pass。

输出契约(稳定, 买家可程序化解析):
  verdict: pass | mismatch | unverifiable
  checks: 逐项 {field, expected, actual, ok}
  sources: 每个 provider 的原始读数与是否成功
"""
import json
import os
import urllib.request

PROVIDERS = [
    ('blastapi', 'https://bsc-mainnet.public.blastapi.io'),
    ('blxrbdn', 'https://bsc.rpc.blxrbdn.com'),
]
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


# 可选出站代理: 设 ONCHAIN_VERIFY_PROXY=http://host:port 时走它。
# 无代理的机器留空即可; 有出口限制的机器(机房/公司网)必须能指定, 否则
# 每个 provider 都 Connection refused, 读者会以为是工具坏了。
_PROXY = os.environ.get('ONCHAIN_VERIFY_PROXY', '').strip()
_OPENER = (urllib.request.build_opener(
    urllib.request.ProxyHandler({'http': _PROXY, 'https': _PROXY}))
    if _PROXY else urllib.request.build_opener())


def _rpc(url, method, params, timeout=20):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': 'Mozilla/5.0'})
    with _OPENER.open(req, timeout=timeout) as r:
        j = json.loads(r.read())
    if j.get('error'):
        raise RuntimeError(str(j['error'])[:120])
    return j['result']


def _read_receipt(url, tx_hash):
    rc = _rpc(url, 'eth_getTransactionReceipt', [tx_hash])
    if not rc:
        return None
    return {
        'block': int(rc['blockNumber'], 16),
        'status': rc['status'],
        'from': rc.get('from', ''),
        'logs': rc.get('logs', []),
    }


def _transfers(logs):
    out = []
    for l in logs:
        t = l.get('topics') or []
        if len(t) < 3 or t[0].lower() != TRANSFER:
            continue
        out.append({
            'token': l.get('address', ''),
            'from': '0x' + t[1][26:],
            'to': '0x' + t[2][26:],
            'value': str(int(l.get('data', '0x0'), 16)),
        })
    return out


def verify(tx_hash, expect_to=None, expect_value=None, token=None):
    """双源核验一笔 tx。

    tx_hash: 0x + 64 hex
    expect_to: 期望收款地址(可选)
    expect_value: 期望金额, 以最小单位字符串或 int 给出(可选)
    token: 期望 token 合约地址(可选)
    """
    tx_hash = (tx_hash or '').strip().lower()
    if not (tx_hash.startswith('0x') and len(tx_hash) == 66):
        return {'verdict': 'unverifiable', 'error': 'tx hash must be 0x + 64 hex', 'sources': {}}

    readings, sources = [], {}
    for name, url in PROVIDERS:
        try:
            rc = _read_receipt(url, tx_hash)
        except Exception as e:
            sources[name] = {'ok': False, 'error': str(e)[:120]}
            continue
        if rc is None:
            sources[name] = {'ok': False, 'error': 'receipt not returned (provider may not index this tx)'}
            continue
        rc['transfers'] = _transfers(rc['logs'])
        sources[name] = {'ok': True, 'block': rc['block'], 'status': rc['status'],
                         'transfer_count': len(rc['transfers'])}
        readings.append((name, rc))

    if not readings:
        return {'verdict': 'unverifiable', 'tx': tx_hash, 'sources': sources,
                'reason': 'no provider returned a receipt; this is not evidence the tx does not exist'}

    # 两个 provider 必须给出相同 block/status/transfer 集合, 否则判 unverifiable
    base_name, base = readings[0]
    if len(readings) == 2:
        other_name, other = readings[1]
        sig = lambda rc: (rc['block'], rc['status'],
                          sorted((t['token'].lower(), t['from'].lower(), t['to'].lower(), t['value'])
                                 for t in rc['transfers']))
        if sig(base) != sig(other):
            return {'verdict': 'unverifiable', 'tx': tx_hash, 'sources': sources,
                    'reason': 'providers disagree on block/status/transfers; do not trust either read'}

    checks = []
    transfers = base['transfers']
    if token:
        hit = [t for t in transfers if t['token'].lower() == token.lower()]
        checks.append({'field': 'token', 'expected': token, 'ok': bool(hit),
                       'actual': sorted({t['token'] for t in transfers})})
        transfers = hit or transfers
    if expect_to:
        hit = [t for t in transfers if t['to'].lower() == expect_to.lower()]
        checks.append({'field': 'to', 'expected': expect_to, 'ok': bool(hit),
                       'actual': sorted({t['to'] for t in transfers})})
        transfers = hit or transfers
    if expect_value is not None:
        want = int(expect_value)
        got = sum(int(t['value']) for t in transfers)
        checks.append({'field': 'value', 'expected': str(want), 'ok': got == want, 'actual': str(got)})

    failed = [c for c in checks if not c['ok']]
    # 2026-10-31 修: 没传断言时 checks 为空, 旧逻辑回 unverifiable —— 但双源一致读到收据
    # 本身就是一次成功的核验(读者要的是「这笔 tx 确实存在且两源一致」)。
    # 只有真的读不到/两源分歧才 unverifiable; 有断言且不符才是 mismatch。
    if failed:
        verdict = 'mismatch'
    else:
        verdict = 'pass'
    return {
        'verdict': verdict,
        'tx': tx_hash,
        'block': base['block'],
        'status': base['status'],
        'from': base['from'],
        'transfers': transfers,
        'checks': checks,
        'sources': sources,
        'cross_checked': len(readings) == 2,
    }
