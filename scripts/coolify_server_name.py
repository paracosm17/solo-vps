#!/usr/bin/env python3
"""Initialize the built-in Coolify server name without owning custom UI names."""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess


def desired_name(server: dict, admin_user: str, hostname: str) -> str:
    if len(hostname) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in hostname.split('.')):
        raise ValueError("Invalid configured hostname")
    if (server.get('id'), server.get('team_id'), server.get('ip'), server.get('user')) != (0, 0, 'host.docker.internal', admin_user):
        raise ValueError("Unexpected built-in server identity")
    name = server.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError("Missing server display name")
    return hostname if name == 'localhost' else name


def execute(docker: str, admin_user: str, hostname: str) -> dict:
    # Validate before invoking the platform, including safe argument transport.
    desired_name(dict(id=0, team_id=0, ip='host.docker.internal', user=admin_user, name='localhost'), admin_user, hostname)
    payload = base64.b64encode(json.dumps(dict(admin_user=admin_user, hostname=hostname)).encode()).decode()
    php = r'''<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
try {
    $input=json_decode(base64_decode('__PAYLOAD__'),true,512,JSON_THROW_ON_ERROR);
    $result=Illuminate\Support\Facades\DB::transaction(function () use ($input) {
        $servers=App\Models\Server::where('id',0)->lockForUpdate()->get();
        if ($servers->count()!==1) throw new RuntimeException('Missing built-in server');
        $server=$servers->first();
        if ($server->id!==0 || $server->team_id!==0 || $server->ip!=='host.docker.internal' || $server->user!==$input['admin_user']) throw new RuntimeException('Unexpected built-in server');
        $changed=$server->name==='localhost' && $server->name!==$input['hostname'];
        if ($changed) { $server->name=$input['hostname']; $server->save(); }
        return ['changed'=>$changed];
    });
    echo 'SOLO_VPS_SERVER_NAME:'.json_encode($result);
} catch (Throwable $error) { fwrite(STDERR,"Server name initialization failed; details suppressed\n"); exit(2); }
'''.replace('__PAYLOAD__', payload)
    result = subprocess.run([docker, 'exec', '-i', 'coolify', 'php'], input=php, text=True, capture_output=True, timeout=120)
    marker = 'SOLO_VPS_SERVER_NAME:'
    if result.returncode or marker not in result.stdout:
        raise ValueError('Native server name initialization failed; inspect private platform logs')
    output = json.loads(result.stdout.split(marker, 1)[1])
    if not isinstance(output.get('changed'), bool):
        raise ValueError('Missing native name evidence')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', default='/usr/bin/docker')
    parser.add_argument('--admin-user', required=True)
    parser.add_argument('--hostname', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.docker, args.admin_user, args.hostname)))
    except (ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
