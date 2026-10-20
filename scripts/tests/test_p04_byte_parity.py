import json
from unittest.mock import patch
from scripts.dashboard import config


def test_existing_tool_resolution_unchanged_and_iqtree_aliases_available():
    for alias in ('iqtree2', 'iqtree3', 'iqtree'):
        def which(name, path=None):
            return '/tools/' + name if name != 'iqtree2' or alias == 'iqtree2' else None
        if alias == 'iqtree':
            def which(name, path=None):
                return None if name in ('iqtree2', 'iqtree3') else '/tools/' + name
        with patch.object(config.shutil, 'which', side_effect=which):
            response = config.get_preflight_status()
        iqtree = next(tool for tool in response['tools'] if tool['name'] == 'iqtree2')
        assert iqtree['present'] and iqtree['path'] == '/tools/' + alias
        for tool in response['tools']:
            if tool['name'] != 'iqtree2':
                assert json.dumps(tool['path']).encode() == json.dumps('/tools/' + tool['name']).encode()
