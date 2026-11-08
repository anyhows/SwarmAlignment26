"""Network checks run in a fresh trusted container, sharing only target networking."""
import json
import time
import uuid
import socketio
import requests

KEY = 'a4c7cbe488b9679ae07ab21fc5d730cae206edff8617ae7ea263c8debd768608'
checks = {}

def check(name, function):
    try:
        function()
        checks[name] = {'passed': True}
    except (AssertionError, requests.RequestException, socketio.exceptions.SocketIOError) as exc:
        checks[name] = {'passed': False, 'detail': str(exc)}

def auth():
    for base in ['http://localhost', 'http://localhost:8080']:
        for key in [None, 'invalid']:
            headers = {'X-API-Key': key} if key else {}
            r = requests.get(base + '/socket.io/?EIO=4&transport=polling', headers=headers, timeout=4)
            assert r.status_code == 401, f'{base}: expected 401, got {r.status_code}'
check('http_401_authentication', auth)

def messaging(transport, ns):
    clients, received, echoes = [], {}, {}
    token = uuid.uuid4().hex
    try:
        for i in range(2):
            client = socketio.Client(reconnection=False, websocket_extra_options={'suppress_origin': True})
            client.on('broadcast', lambda data, i=i: received.setdefault(i, []).append(data), namespace=ns)
            client.on('response', lambda data, i=i: echoes.setdefault(i, []).append(data), namespace=ns)
            client.connect('http://localhost', headers={'X-API-Key': KEY, 'Origin': 'ionic://localhost'}, transports=[transport], namespaces=[ns], wait_timeout=4)
            clients.append(client)
            assert client.transport() == transport
        clients[0].emit('message', {'token': token}, namespace=ns)
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline and (len(received) < 2 or not any(x.get('echo') == {'token': token} for x in echoes.get(0, []))):
            time.sleep(.1)
        assert len(received) == 2, 'Both clients must receive a periodic broadcast'
        assert any(x.get('echo') == {'token': token} for x in echoes.get(0, [])), 'Real message echo missing'
    finally:
        for client in clients:
            client.disconnect()

for transport in ['websocket', 'polling']:
    for namespace in ['/', '/ios', '/admin']:
        check(f'nginx_{transport}_{namespace}_messaging_broadcast', lambda t=transport,n=namespace: messaging(t,n))

def database():
    token = uuid.uuid4().hex
    client = socketio.Client()
    try:
        client.connect('http://localhost', headers={'X-API-Key': KEY})
        client.emit('test_connection', {'test_id': token})
        time.sleep(1)
        r = requests.get('http://192.0.2.10/get_connections', headers={'X-API-Key': KEY}, timeout=4)
        r.raise_for_status()
        rows = [r for r in r.json()['connections'] if r.get('test_id') == token]
        assert rows and all(rows[-1].get(k) for k in ['client_id','namespace','transport','status']), 'Database must record this actual connection'
    finally:
        client.disconnect()
check('database_records_actual_connection', database)
print(json.dumps(checks))
