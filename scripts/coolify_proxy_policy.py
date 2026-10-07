#!/usr/bin/env python3
"""Persist the host edge policy through Coolify's native proxy lifecycle.

Configuration and Docker inspection stay private; stdout contains booleans only.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

PORTS = ['80:80/tcp', '443:443/tcp']
LEGACY_HEADER = '# Managed by Solo VPS: proxy TCP edge policy v1.'


class PolicyError(ValueError):
    pass


def policy_configuration(configuration: str) -> tuple[str, bool]:
    data = yaml.safe_load(configuration)
    if not isinstance(data, dict) or not isinstance(data.get('services'), dict):
        raise PolicyError('Invalid native proxy configuration')
    proxy = data['services'].get('traefik')
    if not isinstance(proxy, dict) or proxy.get('container_name') != 'coolify-proxy':
        raise PolicyError('Unknown proxy service identity')
    labels = proxy.get('labels', {})
    if isinstance(labels, list):
        labels = dict(item.split('=', 1) for item in labels if isinstance(item, str) and '=' in item)
    if not isinstance(labels, dict) or str(labels.get('coolify.proxy')).lower() != 'true':
        raise PolicyError('Unknown proxy ownership')
    if not str(proxy.get('image', '')).startswith('traefik:') or proxy.get('network_mode') == 'host':
        raise PolicyError('Unsupported proxy image or network mode')
    if proxy.get('ports') == PORTS:
        return configuration, False
    # Node marks locate only ports; never reserialize operator YAML values.
    # Compose and PyYAML disagree on YAML 1.1 scalars such as on/off.
    def field(node, name):
        if not isinstance(node, yaml.MappingNode):
            raise PolicyError('Unsupported proxy YAML shape')
        matches = [(key, value) for key, value in node.value if key.value == name]
        if len(matches) != 1:
            raise PolicyError('Missing or ambiguous proxy YAML field')
        return matches[0][1]
    document = yaml.compose(configuration)
    service_node = field(field(document, 'services'), 'traefik')
    port_nodes = [(key, value) for key, value in service_node.value if key.value == 'ports']
    if len(port_nodes) > 1 or service_node.flow_style:
        raise PolicyError('Ambiguous or unsupported inline proxy service')
    replacement = json.dumps(PORTS)
    if port_nodes:
        key_node, node = port_nodes[0]
        if node.start_mark.index <= key_node.end_mark.index or configuration[node.start_mark.index:node.end_mark.index].startswith('&'):
            raise PolicyError('Shared proxy port aliases require operator review')
        if isinstance(node, yaml.SequenceNode) and not node.flow_style:
            replacement += '\n' + ' ' * node.end_mark.column
        text = configuration[:key_node.end_mark.index] + ': ' + replacement + configuration[node.end_mark.index:]
    else:
        position = service_node.start_mark
        text = configuration[:position.index] + 'ports: ' + replacement + '\n' + ' ' * position.column + configuration[position.index:]
    if yaml.safe_load(text)['services']['traefik']['ports'] != PORTS:
        raise PolicyError('Proxy port patch did not roundtrip')
    return text, True


def run(args: list[str], stdin: str | None = None) -> str:
    result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise PolicyError('Native proxy operation failed; inspect private local runtime state')
    return result.stdout


def native(docker: str, payload: dict) -> dict:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    php = r'''<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
try {
    $input=json_decode(base64_decode('__PAYLOAD__'),true,512,JSON_THROW_ON_ERROR);
    $servers=App\Models\Server::where('ip','host.docker.internal')->where('user',$input['admin_user'])->get();
    if ($servers->count()!==1) throw new RuntimeException('Unknown localhost');
    $server=$servers->first();
    if ($server->proxyType()!==App\Enums\ProxyTypes::TRAEFIK->value) throw new RuntimeException('Unknown proxy');
    if ($input['mode']==='check') {
        $configuration=$server->proxy->get('last_saved_proxy_configuration');
        if (!is_string($configuration) || trim($configuration)==='') throw new RuntimeException('Missing native policy');
    } else {
        $configuration=App\Actions\Proxy\GetProxyConfiguration::run($server);
        if ($input['mode']==='save') {
            if (!hash_equals($input['original_sha256'],hash('sha256',$configuration))) throw new RuntimeException('Configuration changed concurrently');
            App\Actions\Proxy\SaveProxyConfiguration::run($server,$input['configuration']);
            $configuration=$input['configuration'];
        }
        if ($input['restart'] ?? false) App\Actions\Proxy\StartProxy::run($server,false);
    }
    echo "SOLO_VPS_PROXY_JSON:".json_encode(['configuration'=>$configuration]);
} catch (Throwable $error) { fwrite(STDERR,"Native proxy policy failed; details suppressed\n"); exit(2); }
'''.replace('__PAYLOAD__', encoded)
    output = run([docker, 'exec', '-i', 'coolify', 'php'], php)
    marker = 'SOLO_VPS_PROXY_JSON:'
    if marker not in output:
        raise PolicyError('Native proxy returned no policy evidence')
    return json.loads(output.split(marker, 1)[1])


def proxy_state(docker: str) -> dict | None:
    ids = run([docker, 'container', 'ls', '--all', '--filter', 'name=^/coolify-proxy$', '--format', '{{.ID}}'])
    if not ids.strip():
        return None
    rows = json.loads(run([docker, 'container', 'inspect', 'coolify-proxy']))
    if len(rows) != 1:
        raise PolicyError('Ambiguous proxy container')
    value = rows[0]
    config = value.get('Config', {})
    labels = config.get('Labels', {})
    if value.get('Name') != '/coolify-proxy' or labels.get('coolify.proxy') != 'true' or labels.get('com.docker.compose.service') != 'traefik' or not config.get('Image', '').startswith('traefik:') or value.get('HostConfig', {}).get('NetworkMode') == 'host':
        raise PolicyError('Unknown proxy container ownership')
    return value


def safe_publications(value: dict) -> bool:
    locations = [value.get('HostConfig', {}).get('PortBindings', {})]
    if value.get('State', {}).get('Running'):
        locations.append(value.get('NetworkSettings', {}).get('Ports', {}))
    for ports in locations:
        published = {key: bindings for key, bindings in ports.items() if bindings}
        if set(published) != {'80/tcp', '443/tcp'}:
            return False
        for key, bindings in published.items():
            if not isinstance(bindings, list) or any(not isinstance(binding, dict) or binding.get('HostIp') not in ('', '0.0.0.0', '::') or binding.get('HostPort') != key.split('/')[0] for binding in bindings):
                return False
    return True


def execute(docker: str, admin_user: str, apply: bool, override: Path) -> dict:
    if override.is_symlink() or (override.exists() and (not override.is_file() or not override.read_text().startswith(LEGACY_HEADER))):
        raise PolicyError('Unknown operator proxy override; preserve and review it')
    before = proxy_state(docker)
    original = native(docker, {'mode': 'get' if apply else 'check', 'admin_user': admin_user})['configuration']
    configuration, changed = policy_configuration(original)
    restart = bool(before and before.get('State', {}).get('Running') and not safe_publications(before))
    if not apply and (changed or restart):
        raise PolicyError('Native proxy policy or running publications drifted')
    if restart:
        model = json.loads(run([docker, 'compose', '--project-directory', '/data/coolify/proxy', '-f', '-', 'config', '--format', 'json'], configuration))
        if model['services']['traefik']['image'] != before['Config']['Image']:
            raise PolicyError('Native saved configuration would change the running proxy image')
        networks = {network.get('name', key) for key, network in model.get('networks', {}).items()}
        if set(before.get('NetworkSettings', {}).get('Networks', {})) - networks:
            raise PolicyError('Native restart needs review of extra attached application networks')
    if apply and (changed or restart):
        native(docker, {'mode': 'save', 'admin_user': admin_user, 'configuration': configuration, 'original_sha256': hashlib.sha256(original.encode()).hexdigest(), 'restart': restart})
    persisted = native(docker, {'mode': 'check', 'admin_user': admin_user})['configuration']
    if policy_configuration(persisted)[1]:
        raise PolicyError('Native saved policy did not persist')
    after = proxy_state(docker)
    if before and before.get('State', {}).get('Running'):
        if not after or not safe_publications(after):
            raise PolicyError('Running proxy publications remain unsafe')
        if before['Config']['Image'] != after['Config']['Image'] or before['Image'] != after['Image']:
            raise PolicyError('Native restart changed the proxy image; review it before proceeding')
        if set(before.get('NetworkSettings', {}).get('Networks', {})) - set(after.get('NetworkSettings', {}).get('Networks', {})):
            raise PolicyError('Native restart lost an attached network; inspect resource connectivity')
    removed = False
    if apply and override.exists():
        override.unlink()
        removed = True
    return {'changed': changed or restart or removed, 'native_policy_safe': True, 'restarted': restart, 'legacy_override_removed': removed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', default='/usr/bin/docker')
    parser.add_argument('--admin-user', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--legacy-override', type=Path, default=Path('/data/coolify/proxy/docker-compose.override.yml'))
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.docker, args.admin_user, args.apply, args.legacy_override)))
    except (PolicyError, OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError, subprocess.TimeoutExpired):
        print('ERROR: native Coolify proxy policy failed; private configuration suppressed', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
